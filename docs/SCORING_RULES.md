# Reglas de calificación (`points-v1`)

La política es `PointsGradingPolicy` (`assessments/domain/services.py`). Cada evaluación guarda sus factores con código, puntos y detalle, y los devuelve `GET /api/v1/risk-assessments/{auctionId}`. Así cualquier nota se puede explicar.

## Datos que usa

| Fuente | Qué aporta | Cada cuánto |
|---|---|---|
| Padrón reducido del RUC (SUNAT) | Si el RUC existe, estado, condición del domicilio, razón social | Diario |
| Agentes de retención y percepción del IGV (datos abiertos) | Si SUNAT lo designó agente | Mensual |
| La subasta (`AuctionCreated`) | RUC y nombre del pagador según la factura, vencimiento | En cada evento |

Ningún archivo de SUNAT trae la fecha de inscripción del RUC, así que la antigüedad no cuenta.

## 1. Filtro: la factura no es elegible

| Código | Cuándo |
|---|---|
| `PAYER_NOT_IN_REGISTRY` | El RUC del pagador no figura en el padrón |
| `PAYER_NOT_ACTIVE` | El estado no es `ACTIVO` (baja, suspensión…) |
| `PAYER_DOMICILE_NOT_FOUND` | La condición es `NO HABIDO` o `NO HALLADO…` |

La subasta pasa a `REJECTED` en Investment con el código y el motivo, y la MYPE lo ve en el detalle de su factura.

## 2. Puntos: se parte de 40

| Código | Puntos | Cuándo |
|---|---|---|
| `WITHHOLDING_AGENT` | +20 | Agente de retención del IGV |
| `PERCEPTION_AGENT` | +10 | Agente de percepción (solo si no es de retención) |
| `DOMICILE_FOUND` | +10 | Condición `HABIDO` |
| `DOMICILE_UNVERIFIED` | −10 | Condición `PENDIENTE` o `POR VERIFICAR` |
| `COMPANY` | +5 | RUC 20 (persona jurídica) |
| `INDIVIDUAL` | −5 | RUC 10 (persona natural con negocio) |
| `NAME_MATCHES` | +5 | La razón social de la factura coincide con la de SUNAT (similitud ≥ 0,85) |
| `NAME_MISMATCH` | −15 | No coincide |
| `TERM_UP_TO_30_DAYS` | +10 | Vence en 30 días o menos |
| `TERM_31_TO_60_DAYS` | +5 | Vence en 31 a 60 días |
| `TERM_61_TO_90_DAYS` | 0 | Vence en 61 a 90 días |
| `TERM_OVER_90_DAYS` | −10 | Vence en más de 90 días |

Para comparar nombres se pasan a mayúsculas y se quitan tildes, puntuación y la forma societaria (S.A.C., S.R.L., E.I.R.L., «Sociedad Anónima Cerrada»…). Así «Pagador S.A.C.» y «PAGADOR SOCIEDAD ANONIMA CERRADA» coinciden.

## 3. Nota

| Puntaje | Nota |
|---|---|
| 75 o más | A |
| 55 a 74 | B |
| Menos de 55 | C |

Ejemplos:

- Empresa habida, nombre que coincide, 45 días: 40 + 10 + 5 + 5 + 5 = **65 → B**.
- Lo mismo, pero agente de retención: **85 → A**.
- Nombre que no coincide: **45 → C**.

## Sin padrón

Mientras el padrón no se haya cargado nunca, cada subasta sale **C** con el factor `REGISTRY_UNAVAILABLE`. Nunca se rechaza por falta de datos.

## Cambiar las reglas

Se escribe una política nueva (o una versión nueva, `points-v2`) en `assessments/domain/services.py`, con sus tests, y se devuelve en `build_grading_policy()`. Las evaluaciones ya emitidas conservan su `grading_policy`.
