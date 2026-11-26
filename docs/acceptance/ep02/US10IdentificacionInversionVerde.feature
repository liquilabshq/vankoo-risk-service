# language: es
@EP02 @US10 @servicio_risk
Característica: Identificación de inversión verde
  Como inversionista
  Quiero identificar las empresas con certificación ambiental
  Para realizar inversiones responsables

  # Reglas green-v1 (docs/GREEN_RULES.md): la IA solo transcribe el certificado;
  # deciden cinco reglas fijas contra SUNAT y OEFA.

  Escenario: Asignar el distintivo Factoring Verde a una MYPE certificada
    Dado que la MYPE subió a su perfil un certificado con estos datos:
      | campo       | valor                   |
      | norma       | ISO 14001               |
      | titular     | Textiles Andinos S.A.C. |
      | RUC         | 20512345678             |
      | vencimiento | dentro de 8 meses       |
    Y el titular coincide con la razón social de SUNAT para ese RUC
    Y el RUC no figura en el registro de infractores de OEFA
    Cuando se evalúa una subasta elegible de esa MYPE
    Entonces el estado verde de la subasta es "GREEN"
    Y la subasta muestra el distintivo "Factoring Verde"
    Y se registran los criterios que lo sustentan:
      | criterio                   | resultado |
      | CERTIFICATE_READABLE       | cumple    |
      | ACCEPTED_STANDARD          | cumple    |
      | IN_FORCE                   | cumple    |
      | HOLDER_MATCHES_SUNAT       | cumple    |
      | NOT_ENVIRONMENTAL_OFFENDER | cumple    |

  Esquema del escenario: No asignar el distintivo y conservar el motivo
    Dado que la MYPE <situación del certificado>
    Cuando se evalúa una subasta elegible de esa MYPE
    Entonces el estado verde de la subasta es "<estado>"
    Y la subasta no muestra el distintivo "Factoring Verde"
    Y la evaluación conserva el motivo de la decisión

    Ejemplos:
      | situación del certificado                             | estado                 |
      | nunca subió un certificado                            | NO_CERTIFICATE         |
      | subió un certificado ISO 9001                         | NOT_GREEN              |
      | tenía un certificado verde que ya venció              | EXPIRED                |
      | tenía un certificado verde, pero ahora figura en OEFA | ENVIRONMENTAL_OFFENDER |
