# Functions

Esta carpeta agrupa los agentes y utilidades de soporte.

Todo agente nuevo de Mediprocesos que se cree a partir de ahora debe vivir dentro de esta carpeta.

## Convención recomendada

- Un agente por carpeta.
- Cada agente debe tener su propio `README.md`.
- Las credenciales de Firebase deben vivir en `functions/script/keys/`.
- No guardar secretos reales en el repositorio.
- No crear agentes nuevos fuera de `AGENTES_MEDI` salvo una excepción acordada por el equipo.

## Agente base disponible

- `agentBaseMediprocesos/`
  Plantilla inicial para crear nuevos agentes siguiendo el patrón observado en `Alizia`.

- `main.py`
  Ejemplo base de Firebase Functions para publicar un agente como API HTTP.

## Auditoría médica

- `agentAuditoriaMedica/`
  Revisa pertinencia clínica de medicamentos, laboratorios y procedimientos con
  búsqueda de fuentes médicas. Usa una proyección de datos clínicos y entrega
  hallazgos JSON para revisión humana. Consulte su `README.md` para contrato,
  seguridad y despliegue del endpoint `auditoria_medica_api`.
