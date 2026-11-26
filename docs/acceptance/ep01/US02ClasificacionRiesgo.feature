# language: es
@EP01 @US02 @servicio_risk
Característica: Clasificación de riesgo de la operación
  Como empresario MYPE
  Quiero conocer la clasificación de riesgo de mi factura
  Para saber si puede publicarse y comunicar sus condiciones a los inversionistas

  # Reglas points-v3 (docs/SCORING_RULES.md): se parte de 40 puntos;
  # 75 o más es A, de 55 a 74 es B y menos de 55 es C.

  Esquema del escenario: Calificar una factura elegible según la solvencia del pagador
    Dado que se creó una subasta cuyo pagador figura en el padrón de SUNAT como "ACTIVO" y "HABIDO"
    Y el pagador tiene estas características:
      | característica            | valor                 |
      | tipo de RUC               | <tipo de RUC>         |
      | agente de retención       | <agente de retención> |
      | razón social coincide     | <razón social>        |
      | días hasta el vencimiento | <días>                |
      | central de riesgos        | <central>             |
    Cuando el servicio de riesgo evalúa la subasta
    Entonces el puntaje es <puntaje> y la clasificación es "<clasificación>"
    Y la evaluación guarda cada factor con su código y sus puntos
    Y la subasta pasa a "DRAFT" para que la MYPE pueda cotizarla

    Ejemplos:
      | tipo de RUC | agente de retención | razón social | días | central | puntaje | clasificación |
      | 20          | sí                  | sí           | 45   | Normal  | 85      | A             |
      | 20          | no                  | sí           | 45   | Normal  | 65      | B             |
      | 20          | no                  | sí           | 45   | CPP     | 55      | B             |
      | 20          | no                  | no           | 45   | Normal  | 45      | C             |

  Esquema del escenario: Rechazar una factura cuyo pagador no es elegible
    Dado que se creó una subasta cuyo pagador <situación>
    Cuando el servicio de riesgo evalúa la subasta
    Entonces la subasta pasa a "REJECTED" con el código "<código>"
    Y la MYPE ve el motivo del rechazo en el detalle de su factura
    Y la operación no se publica en el marketplace

    Ejemplos:
      | situación                                    | código                   |
      | no figura en el padrón de SUNAT              | PAYER_NOT_IN_REGISTRY    |
      | fue declarado sin capacidad operativa (SSCO) | PAYER_SHELL_COMPANY      |
      | tiene un estado distinto de "ACTIVO"         | PAYER_NOT_ACTIVE         |
      | tiene la condición "NO HABIDO"               | PAYER_DOMICILE_NOT_FOUND |

  Escenario: Calificar con prudencia cuando falta información del pagador
    Dado que el padrón de SUNAT todavía no terminó su primera carga
    Cuando el servicio de riesgo evalúa una subasta
    Entonces la clasificación es "C" con el motivo "padrón no disponible"
    Y la subasta no se rechaza
