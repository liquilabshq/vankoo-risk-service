# Arquitectura

## Contextos

Dos contextos acotados, cada uno con las cuatro capas de la skill `ddd-fastapi`:

- `assessments` decide sobre cada subasta.
- `registries` guarda la copia local de los padrones de SUNAT y de las listas de sanciones (SUNAT, OECE, OEFA).

`assessments` le pregunta a `registries` solo por su fachada (`registries/interfaces/acl.py`), a través de `assessments/application/acl.py`, que es el único módulo que la importa.

### `assessments`

| Capa | Qué hay |
|---|---|
| `domain/` | El agregado `RiskAssessment`, sus value objects (`Ruc`, `RiskGrade`, `PayerStanding`, `ScoreFactor`, `GradingDecision`…), el evento `RiskAssessmentIssued` y la política `PointsGradingPolicy` |
| `application/` | `RiskAssessmentApplicationService` (evaluar, entregar, leer), el puerto `AuctionEvaluationService` hacia Investment (calificar o rechazar), el puerto `CreditBureau` (la central de riesgos), el puerto `NewsScreener` (noticias negativas) y `ExternalRegistriesService` (la ACL hacia `registries`) |
| `infrastructure/` | Tablas, repositorio SQLAlchemy, el adaptador httpx de Investment y `SimulatedCreditBureau` (la única pieza **simulada** del servicio) y `OpenAINewsScreener` (búsqueda web con `gpt-6-luna`, con caché de 7 días en `news_screenings`) |
| `interfaces/` | Consumidor de Kafka, repartidor, rutas REST y el parser del contrato |

### `registries`

| Capa | Qué hay |
|---|---|
| `domain/` | `RegistrySnapshot` (qué versión de cada fuente está cargada) y un registro por fuente (`TaxpayerRecord`, `AgentRecord`, `ShellCompanyRecord`, `CoactiveDebtorRecord`, `OeceSanctionRecord`, `EnvironmentalOffenderRecord`) |
| `application/` | `RegistryRefreshService`: compara la versión publicada (`Last-Modified`) con la cargada y, si cambió, descarga y reemplaza |
| `infrastructure/` | Lectores de cada formato (`parsers.py`: TXT latin-1, CSV, XLSX, JSON), descarga con httpx y carga masiva con `COPY` e intercambio atómico de tablas (`bulk.py`) |
| `interfaces/` | La fachada para `assessments`, el comando `python -m registries refresh` y el programador diario |

La carga del padrón (1,6 GB, unos 18 M de filas) corre siempre en **otro proceso**, nunca en el bucle de eventos de la API. Escribe en una tabla nueva y la intercambia por la vieja en la misma transacción: hasta el commit se sigue leyendo la copia anterior, y si algo falla queda intacta.

### `shared`

`shared/` es el núcleo compartido de la skill, más tres piezas técnicas que la skill no trae:

- la **bandeja de eventos procesados** (`processed_events`);
- la tabla de **dead letters**;
- un **supervisor de tareas en segundo plano**, más `/health`.

## Flujo

```mermaid
sequenceDiagram
    participant INV as Investment
    participant K as Kafka
    participant C as Consumidor
    participant DB as PostgreSQL
    participant W as Repartidor

    INV->>K: AuctionCreated (investment.auction-lifecycle.v1)
    K->>C: mensaje
    C->>DB: consulta el padrón (registries)
    C->>DB: evaluación + eventId procesado (una transacción)
    C->>K: confirma el offset
    C-->>W: RiskAssessmentIssued (lo despierta)
    W->>INV: PUT …/evaluation (elegible) o POST …/rejection (no elegible)
    INV-->>W: 200 (subasta en DRAFT o REJECTED)
    W->>DB: DELIVERED
```

## Garantías

- **Al menos una vez.** Kafka puede repetir un mensaje. El `eventId` se guarda en `processed_events` en la misma transacción que la evaluación, así que un evento repetido no crea otra. Además, `auction_id` es único: una evaluación por subasta.
- **El offset se confirma después de guardar.** Si el servicio cae a mitad, el mensaje vuelve y la bandeja lo reconoce.
- **Nada se descarta en silencio.** Van a `dead_letters`, con el motivo, y se confirman para no bloquear el tópico:
  - un JSON ilegible;
  - un `eventType` o un `schemaVersion` desconocido;
  - un hecho que el dominio rechaza (un RUC que no tiene 11 dígitos).

  Los otros seis eventos del contrato se saltan sin escribir nada.
- **Errores transitorios.** Si la base de datos no responde, el mismo mensaje se reintenta (1 s, 2 s… hasta 60 s) sin confirmar el offset. La partición espera, y así los eventos de una subasta no se desordenan.
- **Entrega con outbox.** La evaluación se guarda primero y se entrega después. Si Investment no responde, espera en `risk_assessments` con reintentos crecientes (1 s, 2 s, 4 s… hasta 5 min). El `assessmentId` y el `assessedAt` se reenvían iguales, y Investment ignora un `assessmentId` que ya aplicó con la misma nota.

| Respuesta de Investment | Estado de la entrega |
|---|---|
| 200 | `DELIVERED` |
| 404, 409 | `REJECTED`: la subasta no existe o ya no admite evaluación |
| 400 | `REJECTED`, con log de error: lo que se envió está mal |
| 5xx, timeout, sin conexión | Sigue `PENDING` y se reintenta |

## Por qué `auto_offset_reset=latest`

El tópico de Investment guarda todo para siempre (`retention.ms=-1`). Un grupo nuevo con `earliest` leería todas las subastas de la historia:

- las que siguen en `DRAFT` se re-evaluarían y **perderían sus cotizaciones**;
- las publicadas devolverían 409;
- las de una base de Oracle ya vaciada devolverían 404.

Con `latest`, el grupo empieza en lo nuevo, y desde entonces sus offsets confirmados dicen dónde seguir.

Para reprocesar a propósito, con el servicio parado:

```bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --group risk-auction-assessment-v1 \
  --topic investment.auction-lifecycle.v1 --reset-offsets --to-datetime 2026-10-14T00:00:00.000 --execute
```

## Un solo proceso

El consumidor y el repartidor corren como tareas supervisadas dentro del `lifespan` de FastAPI: si fallan, se registran y se reinician. Con más de un worker de uvicorn habría consumidores y repartidores duplicados. Se escala con más contenedores en el mismo grupo de Kafka.

## Lo que cambia en las fases siguientes

Nuevas fuentes (certificados verdes) entran como nuevos campos de `PayerStanding` o nuevos puertos, y nuevas reglas en la política. Ver [SCORING_RULES.md](SCORING_RULES.md).
