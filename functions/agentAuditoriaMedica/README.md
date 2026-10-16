# agentAuditoriaMedica

Auditoría de pertinencia clínica de medicamentos frente a los diagnósticos y la edad
del asegurado. Corre como `auditoria_medica_api` en Firebase Functions (`functions/main.py`).
Está pensado para ser llamado por el servicio interno de autorizaciones en staging o
producción; el proyecto Firebase concreto se elige al desplegar (`edge-001` o
`edge-prod-002`). No escribe en Firestore ni cambia autorizaciones.

## Entrada

`POST` con JSON en el formato del integrador: `{"data": {"edad": 49,
"diagnosticos": [...], "medicamentos": [...]}}`. También se acepta el objeto
`data` directamente. `fechaNacimiento` es opcional si la función debe calcular
la edad antes de enviar la proyección al modelo.
Son obligatorios al menos un diagnóstico, un medicamento y una edad calculable o
informada. Máximo 20 diagnósticos y 20 medicamentos.

Antes de llamar a OpenAI, `project_clinical_data` construye una proyección que
contiene **solo edad, diagnósticos y medicamentos**. Si se recibe `fechaNacimiento`,
calcula los años cumplidos al momento de la auditoría según la fecha local de
Guatemala. Este valor tiene prioridad sobre el campo `edad`. Por ejemplo, una
persona nacida el 1976-12-23 tiene 49 años el 2026-09-24. Si falta la fecha de
nacimiento, utiliza `edad` como valor informado. `fechaServicio` se ignora. Solo
se envía la edad numérica; nunca el nombre, carné, fecha de nacimiento, datos del
proveedor, póliza ni códigos internos del medicamento. `laboratorios` y
`procedimientos` se ignoran. La proyección incluye dosis, frecuencia y duración
cuando están presentes. En una autorización histórica, la edad calculada hoy
podría diferir de la edad que tenía la persona cuando recibió el medicamento.

Si falta `compuestoActivo`, el agente consulta la marca y `atc5`; el índice ATC/DDD
del centro colaborador de la OMS permite identificar la sustancia codificada. El
código no confirma por sí solo qué producto se dispensó, por lo que el agente
explicita esa limitación y puede emitir un juicio clínico condicionado. Solo usa
`insuficiente` si falta un dato decisivo para valorar la relación con los
diagnósticos o no encuentra evidencia verificable. El agente pide únicamente
los datos clínicos concretos que cambiarían el juicio del medicamento;
no solicita expediente clínico ni información de póliza. No deduce sexo, embarazo,
tabaquismo, alergias ni otras características ausentes. La evaluación usa
evidencia actual y no valida guías históricas.

## Fuentes y modelo

Usa Responses API con `gpt-6-luna`, `reasoning.effort=medium`,
`text.verbosity=medium`, `web_search` obligatorio y salida con JSON Schema estricto.
La búsqueda se limita a dominios de organismos sanitarios, fichas oficiales y
revisiones sistemáticas (`fda.gov`, `dailymed.nlm.nih.gov`, `nih.gov`, `cdc.gov`,
`who.int`, `nice.org.uk`, `ema.europa.eu`, `acog.org`, `cochranelibrary.com`,
`mspas.gob.gt`, `atcddd.fhi.no`).
Solo se publican enlaces presentes en las fuentes o citas de la respuesta de búsqueda.
Si un medicamento recibe `insuficiente` o no tiene una URL verificable, se hace
una segunda búsqueda centrada en esos ítems. Cuando tampoco se puede verificar
una fuente en ese intento, su juicio pasa a `insuficiente`. Este segundo intento
puede aumentar tokens y tiempo de respuesta. La correspondencia clínica de cada
afirmación aún requiere supervisión médica.
La aplicación que presente el resultado debe mostrar las URLs como enlaces visibles
y clicables.

## Salida

```json
{
  "ok": true,
  "agent": "agentAuditoriaMedica",
  "result": {
    "modelo": "gpt-6-luna",
    "versionContrato": "2.2",
    "fechaAuditoriaUTC": "2026-09-24T12:00:00+00:00",
    "tokensUsados": 1200,
    "tiempoRespuestaSegundos": 4.2,
    "data": {
      "estadoAuditoria": "requiere_revision_clinica",
      "evaluacionMedicaAutorizacion": "objeciones_clinicas",
      "datosEvaluados": {
        "edad": 49,
        "diagnosticos": [{"codigoDiagnostico": "789.09", "icd": "9", "nombreDiagnostico": "Dolor abdominal"}],
        "medicamentos": [{"idItem": "M1", "tipo": "medicamento", "descripcionMedicamento": "Medicamento de ejemplo"}]
      },
      "resumen": {"totalMedicamentos": 1, "compatible": 0, "alerta": 1, "insuficiente": 0, "requierenRevisionClinicaAdicional": 1},
      "hallazgos": [{
        "idItem": "M1",
        "tipo": "medicamento",
        "descripcion": "Medicamento de ejemplo",
        "juicio": "alerta",
        "prioridad": "media",
        "fundamentoClinico": "Ejemplo ilustrativo; no representa un dictamen real.",
        "informacionFaltante": ["Indicación documentada"],
        "fuentes": [{"titulo": "Fuente consultada", "url": "https://www.fda.gov/..."}],
        "requiereRevisionClinicaAdicional": true
      }],
      "nota": "Compatible indica pertinencia clínica razonable con los datos recibidos. La revisión clínica adicional se señala solo para alertas o información decisiva insuficiente. Si la solicitud es histórica, la edad calculada hoy desde el nacimiento puede diferir de la edad al autorizar."
    }
  }
}
```

`datosEvaluados` reproduce únicamente la proyección clínica enviada al modelo:
edad utilizada, diagnósticos y medicamentos. `evaluacionMedicaAutorizacion`
indica si la autorización es congruente con esos datos (`congruente_con_datos`),
presenta objeciones (`objeciones_clinicas`) o no puede determinarse
(`indeterminada`). Es una valoración médica, no una revisión de cobertura.

`resumen.compatible` es el número de medicamentos compatibles, no el dictamen de
toda la solicitud. `compatible` significa pertinencia clínica razonable con la
información disponible; `alerta` identifica una objeción concreta; `insuficiente`
indica que falta un dato decisivo o evidencia verificable.
`requiereRevisionClinicaAdicional` es `false` para un medicamento compatible y
`true` para uno con alerta o insuficiente. El total de estos últimos figura en
`resumen.requierenRevisionClinicaAdicional`. `estadoAuditoria` resume el conjunto:
una alerta tiene prioridad sobre resultados insuficientes, pero cada medicamento
conserva su juicio. Ninguno de estos campos significa aprobación automática.

## Configuración y ejecución

Para pruebas locales, abre `agentAuditoriaMedica/.env` y pega tu clave después de
`OPENAI_API_KEY=`. El agente lee ese archivo automáticamente y da prioridad a la
variable de entorno si ya está configurada. El enlace
`functions/.env.edge-001 -> agentAuditoriaMedica/.env` permite que Firebase CLI
cargue la misma clave como variable de entorno de `edge-001`. El archivo real está
excluido de Git y del paquete de código desplegado; `.env.example` es la plantilla
versionada.

`OPENAI_API_KEY` es la única clave requerida. El endpoint recibe `POST` sin
autenticación (`invoker="public"`). No registrar el cuerpo de la solicitud. La llamada
a OpenAI usa `store=false`. Este flujo utiliza una variable de entorno normal de
Firebase, sin Secret Manager.

```bash
firebase deploy --only functions:auditoria_medica_api --project edge-001
```

Ejemplo mínimo de solicitud:

```bash
curl -X POST "$AUDITORIA_MEDICA_URL" \
  -H 'Content-Type: application/json' \
  --data '{"data":{"edad":49,"diagnosticos":[{"codigoDiagnostico":"789.09","icd":9,"nombreDiagnostico":"Dolor abdominal"}],"medicamentos":[{"compuestoActivo":"DROSPIRENONA, ETINILESTRADIOL","descripcionMedicamento":"YASMIN 21 TABLETAS","dosis":"1 tableta","frecuencia":"24 horas"}]}}'
```

Para ejecutar pruebas locales sin llamar a OpenAI:

```bash
cd functions
venv/bin/python -m unittest discover -s agentAuditoriaMedica/tests -v
```

Errores: `400` para entrada inválida, `405` para método incorrecto y `502` si falla
la auditoría.
