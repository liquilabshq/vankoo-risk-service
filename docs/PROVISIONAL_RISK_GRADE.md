# Nota de riesgo provisional (temporal)

> **Esto es un sustituto, no una evaluación.** Se quita en la fase 2, cuando lleguen las reglas reales.

## Por qué existe

La fase 1 monta el camino completo: Investment publica `AuctionCreated`, este servicio crea la evaluación y se la entrega a Investment, y la subasta pasa a `DRAFT`. Las reglas que miran al pagador (padrón SUNAT, listas de sancionados, central de riesgos simulada y noticias) llegan después.

Mientras tanto, la nota la pone `ProvisionalHashGradePolicy` (`assessments/domain/services.py`). Reemplaza al simulador que tenía Investment (`SimulatedRiskEvaluationHandler`), que ahora está apagado en el compose.

## Qué decide

| Campo | Valor | Por qué |
|---|---|---|
| `riskGrade` | A, B o C, según el SHA-256 del id de la subasta | Variada, para que el mercado muestre TEAs distintas; estable, para que la misma subasta saque siempre la misma |
| `fullBalanceOutstanding` | `true` | El piloto solo acepta facturas con todo el saldo pendiente |
| `grading_policy` | `provisional-hash-v0` | Para reconocerla en los datos |
| `provisional` | `true` | Ídem, también en `GET /api/v1/risk-assessments/{auctionId}` |

**La nota no dice nada del pagador.** Cada evaluación deja en el log un WARNING que empieza por `PROVISIONAL risk grade`.

## Cómo quitarla (fase 2)

1. Escribir la política nueva en `assessments/domain/services.py`, con sus tests.
2. Devolverla en `build_grading_policy()`, en `assessments/interfaces/dependencies.py`.
3. Borrar `ProvisionalHashGradePolicy`, su test y este documento, y quitar el aviso del README.
4. En Investment, borrar `SimulatedRiskEvaluationHandler` según su `docs/SIMULATED_RISK_EVALUATION.md`, y en `vankoo-infra` la variable `INVESTMENT_RISK_SIMULATION_ENABLED`.
5. Decidir qué hacer con las evaluaciones ya emitidas con `provisional = true`.
