# Vankoo Risk Service

Microservicio de evaluación de riesgo de Vankoo. Califica cada subasta de factura con **A, B o C** antes de que la MYPE pueda cotizarla, y le entrega la nota a Investment.

> **Fase 1: la nota es PROVISIONAL.** Sale del id de la subasta y no dice nada del pagador. Existe para que el camino completo (Kafka → evaluación → Investment) funcione antes de las reglas reales. Ver [docs/PROVISIONAL_RISK_GRADE.md](docs/PROVISIONAL_RISK_GRADE.md).

## Qué hace

1. Escucha `AuctionCreated` en el tópico `investment.auction-lifecycle.v1`.
2. Crea una evaluación por subasta y la guarda junto con el evento procesado, en la misma transacción.
3. Se la entrega a Investment con `PUT /api/v1/internal/auctions/{auctionId}/evaluation`, y reintenta mientras Investment no responda.
4. La subasta pasa a `DRAFT` en Investment y la MYPE ya puede cotizarla.

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

Mientras este servicio esté en el compose, el simulador de riesgo de Investment está apagado (`INVESTMENT_RISK_SIMULATION_ENABLED=false`). Así cada subasta se evalúa una sola vez.

## Endpoints

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/v1/risk-assessments/{auctionId}` | La evaluación de una subasta y el estado de su entrega a Investment |
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
