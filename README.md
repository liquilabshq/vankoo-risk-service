# Vankoo Risk Service

Microservicio de evaluación de riesgo de Vankoo. Decide si la factura de cada subasta se puede financiar y, si se puede, la califica con **A, B o C** antes de que la MYPE pueda cotizarla. La decisión se la entrega a Investment.

Califica al **pagador** con datos públicos (padrón de SUNAT, agentes de retención, sujetos sin capacidad operativa, deuda coactiva, sanciones de OECE y OEFA), una central de riesgos **simulada** y reglas de puntos explicables: ver [docs/SCORING_RULES.md](docs/SCORING_RULES.md).

## Qué hace

1. Escucha `AuctionCreated` en el tópico `investment.auction-lifecycle.v1`.
2. Consulta lo que SUNAT dice del pagador en su copia local de los padrones (contexto `registries`).
3. Decide con las reglas de puntos y guarda la evaluación junto con el evento procesado, en la misma transacción.
4. Se la entrega a Investment, y reintenta mientras Investment no responda:
   - si es elegible, con `PUT /api/v1/internal/auctions/{auctionId}/evaluation`: la subasta pasa a `DRAFT` y la MYPE ya puede cotizarla;
   - si no, con `POST /api/v1/internal/auctions/{auctionId}/rejection`: la subasta pasa a `REJECTED` con el motivo.

## Los padrones de SUNAT

El contexto `registries` guarda una copia local de:

- el **padrón reducido del RUC**: unos 18 millones de RUC, con RUC, razón social, estado, condición y ubigeo; unos 2 GB en PostgreSQL;
- el **padrón de agentes de retención y percepción del IGV**: unas 7.800 filas;
- las listas de **sanciones**, que son pequeñas: SSCO de SUNAT (unas 770), deuda coactiva de SUNAT (unas 9.000), inhabilitados y multas de OECE (unas 14.000) e infractores ambientales de OEFA (unos 4.300).

Se actualizan:

```bash
uv run python -m registries refresh                    # los dos
uv run python -m registries refresh --source agents    # solo uno (ver --help)
uv run python -m registries refresh --force            # aunque no haya versión nueva
```

Con el servicio en marcha, se refrescan solos al arrancar y cada día a las 04:00 de Lima. Corren como subproceso para no bloquear la API. Si SUNAT no publicó nada nuevo (mismo `Last-Modified`), no se descarga nada.

La primera carga del padrón descarga unos 400 MB y tarda unos minutos. Mientras tanto, las subastas salen **C** («padrón no disponible») y no se rechazan. La copia anterior sigue en uso hasta que la nueva está entera.

El detalle está en [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Requisitos previos

- Python 3.12 y [uv](https://docs.astral.sh/uv/).
- Docker, para PostgreSQL, Kafka e Investment (el compose de `vankoo-infra`).

## Ejecución local

```bash
uv sync
cp .env.example .env
```

Levantar las dependencias desde `vankoo-infra`:

```bash
docker compose up -d risk-db-postgres kafka-broker investment-service
```

Aplicar las migraciones y arrancar:

```bash
uv run alembic upgrade head
uv run fastapi dev main.py
```

La API queda en `http://localhost:8000` y la documentación en `/docs`.

**Un solo worker.** El consumidor de Kafka y el repartidor viven en el proceso de la API. Con `--workers 2` habría dos de cada uno. Para escalar se levantan más contenedores en el mismo grupo de consumidores.

## Uso con Docker

El servicio está en el compose de `vankoo-infra` como `risk-service` (puerto 8000) con su base `risk-db-postgres` (puerto 5435). Al arrancar, el contenedor aplica las migraciones.

```bash
docker compose up -d --build risk-service
```

## Endpoints

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/v1/risk-assessments/{auctionId}` | La evaluación de una subasta (elegible o no, nota, puntaje, factores) y el estado de su entrega a Investment |
| GET | `/health` | Vivo |
| GET | `/health/ready` | Listo: base de datos, consumidor y repartidor arriba (503 si no) |

No se rutea por el gateway todavía.

## Variables de entorno

| Variable | Por defecto | Para qué |
|---|---|---|
| `DATABASE_URL` | — (obligatoria) | `postgresql+asyncpg://…` |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | `kafka-broker:9094` dentro de Docker |
| `KAFKA_GROUP_ID` | `risk-auction-assessment-v1` | Grupo de consumidores |
| `KAFKA_AUTO_OFFSET_RESET` | `latest` | Dónde empieza un grupo nuevo; ver por qué en la arquitectura |
| `KAFKA_CONSUMER_ENABLED` | `true` | Apagarlo en tests o para solo migrar |
| `INVESTMENT_BASE_URL` | `http://localhost:8082` | Investment directo, nunca el gateway |
| `INVESTMENT_DELIVERY_ENABLED` | `true` | Apagar el repartidor |
| `REGISTRY_REFRESH_ENABLED` | `true` | Refrescar los padrones desde el servicio |
| `REGISTRY_REFRESH_HOUR` | `4` | Hora del refresco diario (zona `REGISTRY_TIMEZONE`, `America/Lima`) |
| `REGISTRY_TAXPAYERS_URL` | el ZIP de SUNAT | Dónde está el padrón reducido |
| `REGISTRY_AGENTS_URL_TEMPLATE` | el ZIP mensual de datos abiertos | Dónde está el padrón de agentes (`{period}` = `YYYYMM`) |
| `REGISTRY_SHELL_COMPANIES_URL`, `REGISTRY_COACTIVE_DEBTORS_URL`, `REGISTRY_OECE_DISQUALIFICATIONS_URL`, `REGISTRY_OECE_FINES_URL`, `REGISTRY_ENVIRONMENTAL_OFFENDERS_URL` | las de SUNAT, OECE y OEFA | Dónde están las listas de sanciones |
| `CREDIT_BUREAU_ENABLED` | `true` | Consultar la central de riesgos **simulada** |
| `DOCS_ENABLED` | `true` | Servir `/docs` |

## Pruebas

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

Los tests usan dobles en memoria: no necesitan PostgreSQL ni Kafka.

## Información adicional

- Sigue la skill `ddd-fastapi`, instalada en `.agents/skills/ddd-fastapi` (se actualiza con `npx skills update`).
- Contrato que consume: `docs/contracts/auction-lifecycle/v1` en `vankoo-investment-service`. Sus ejemplos están copiados en `tests/contracts/`.
- Convenciones del repo: [docs/CONVENTIONS.md](docs/CONVENTIONS.md).
