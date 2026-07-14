# AGENTES_MEDI

Guía base para crear, organizar e iniciar agentes de Mediprocesos usando `OPENAI_API_KEY` y una estructura similar a la de `Alizia/functions/agentATCFinalSync` y `Alizia/functions/agentFinalPertinenciaV4`.

Este repositorio se toma como la base oficial para los agentes futuros de Mediprocesos. Si se crea un agente nuevo en adelante, debe vivir aquí y no mezclarse con agentes legacy de otros proyectos.

## Objetivo

Este repositorio sirve como base para nuevos agentes. La idea es que una persona que va iniciando pueda:

1. Entender qué archivos necesita un agente.
2. Saber para qué sirve cada archivo.
3. Tener una plantilla lista para copiar y adaptar.
4. Trabajar con distintos proyectos Firebase por ambiente.

## Alcance del repositorio

`AGENTES_MEDI` está vacío a propósito para arrancar ordenado.

La intención es que:

- todos los agentes nuevos de Mediprocesos se creen aquí,
- cada agente nuevo salga ya documentado desde el inicio,
- la estructura sea homogénea para facilitar mantenimiento,
- el equipo pueda identificar rápido qué hace cada agente y en qué proyecto se usa.

## Estructura base del repositorio

```text
AGENTES_MEDI/
├── README.md
├── .gitignore
└── functions/
    ├── main.py
    ├── README.md
    ├── requirements.txt
    ├── agentBaseMediprocesos/
    │   ├── README.md
    │   ├── __init__.py
    │   ├── pipeline.py
    │   ├── prompts.py
    │   ├── schemas.py
    │   ├── service.py
    │   └── requirements.txt
    └── script/
        └── keys/
            ├── README.md
            ├── firebase-sa.json
            ├── firebase-sa-prod.json
            └── firebase-sa-staging.json
```

## Qué archivos necesita un agente

Tomando como base `agentATCFinalSync` y `agentFinalPertinenciaV4`, estos son los archivos mínimos recomendados:

- `__init__.py`
  Sirve para que Python trate la carpeta como paquete.

- `pipeline.py`
  Es el archivo principal del agente. Aquí vive la lógica del flujo: validar entrada, preparar contexto, llamar al modelo, transformar la respuesta y devolver el resultado final.

- `prompts.py`
  Guarda los prompts del sistema y del usuario. Separarlo ayuda a mantener el comportamiento del agente sin mezclarlo con la lógica de código.

- `schemas.py`
  Define los modelos de entrada y salida con Pydantic. Esto ayuda a validar datos y a mantener respuestas estructuradas.

- `service.py`
  Funciona como wrapper de entrada. Normalmente expone funciones como `handle_request_payload` o `handle_request_json` para integrarlo con APIs, Cloud Functions o servicios internos.

- `requirements.txt`
  Declara dependencias del agente.

- `README.md`
  Cada agente debe tener su propio README explicando:
  - en qué proyecto o proyectos se usa,
  - cuál es su objetivo,
  - qué recibe de entrada,
  - qué devuelve,
  - cómo se ejecuta,
  - qué dependencias externas usa,
  - si apunta a `edge-001`, producción o staging,
  - quién lo mantiene.

- `functions/main.py`
  Sirve como ejemplo para exponer uno o varios agentes como API HTTP en Firebase Functions. No es parte interna de cada agente, pero sí es la puerta de entrada cuando el agente se publica como endpoint.

## Archivos opcionales según el caso

Estos existen en algunos agentes de referencia y se agregan cuando aplica:

- `run_manual_cases.py`
  Para ejecutar pruebas manuales con payloads específicos.

- `evaluate_effectiveness.py`
  Para medir calidad o desempeño del agente.

- `generate_report.py`
  Para consolidar resultados en CSV o JSONL.

- archivos `.csv`, `.jsonl`, `.json`
  Para reportes, auditorías, pruebas o datos temporales.

## Flujo recomendado para crear un agente nuevo

1. Duplicar `functions/agentBaseMediprocesos/`.
2. Renombrar la carpeta con el nombre del nuevo agente.
3. Actualizar `README.md` del agente.
4. Definir schemas de entrada y salida.
5. Escribir prompts.
6. Implementar lógica en `pipeline.py`.
7. Exponer una interfaz simple en `service.py`.
8. Probar localmente antes de conectarlo a Firebase o a otro backend.

## Regla para agentes nuevos

Todo agente nuevo debe cumplir esta convención mínima:

- vivir dentro de `functions/`,
- tener su propia carpeta,
- tener su propio `README.md`,
- no guardar secretos dentro del código,
- indicar explícitamente si usa `edge-001`, `edge-prod-002` o staging,
- documentar cómo ejecutarlo localmente.

## Cómo trabajar con API Key

No se debe hardcodear la API key en el código.

Usar siempre una variable de entorno:

```bash
export OPENAI_API_KEY="sk-..."
```

Luego ejecutar desde la carpeta del repositorio:

```bash
cd /Users/desarrollomp/Documents/MEDIPROCESOS-PRO/AGENTES_MEDI/functions/agentBaseMediprocesos
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 pipeline.py '{"message":"Hola agente","metadata":{"source":"local"}}'
```

## Cómo publicar un agente como API en Firebase

Se dejó un ejemplo base en [functions/main.py](/Users/desarrollomp/Documents/MEDIPROCESOS-PRO/AGENTES_MEDI/functions/main.py:1).

Ese archivo muestra tres ideas importantes:

- `health_check`
  Endpoint simple para validar que Firebase Functions está levantando.

- `agent_base_api`
  Ejemplo de cómo exponer un agente puntual como endpoint `POST`.

- `example_agent_router`
  Ejemplo de router para manejar varios agentes desde una sola función, usando el campo `agent` del body.

Las dependencias mínimas para este ejemplo quedaron en [functions/requirements.txt](/Users/desarrollomp/Documents/MEDIPROCESOS-PRO/AGENTES_MEDI/functions/requirements.txt:1).

## Para qué sirve `functions/main.py`

`functions/main.py` es la puerta de entrada cuando un agente necesita publicarse como API en Firebase Functions.

No reemplaza la lógica del agente. La lógica sigue viviendo dentro de la carpeta del agente, por ejemplo:

- `pipeline.py`
- `service.py`
- `schemas.py`
- `prompts.py`

Lo que hace `main.py` es:

- recibir la petición HTTP,
- leer el JSON enviado por el cliente,
- llamar al handler del agente,
- devolver la respuesta como JSON,
- manejar errores básicos,
- inicializar Firebase cuando haga falta.

## Flujo recomendado para exponer un agente como API

Cuando un agente de este repositorio deba convertirse en endpoint, la forma recomendada es esta:

1. Crear el agente dentro de `functions/NombreDelAgente/`.
2. Implementar la lógica interna en `pipeline.py`.
3. Exponer una función simple en `service.py`, por ejemplo `handle_request_payload`.
4. Importar ese handler dentro de `functions/main.py`.
5. Crear una función HTTP nueva con `@https_fn.on_request()`.
6. Validar método `POST`.
7. Leer el body con `req.get_json(...)`.
8. Enviar el payload al handler.
9. Retornar la respuesta en formato JSON.
10. Documentar en el README del agente el endpoint, request y response.

## Ejemplo conceptual

El patrón recomendado queda así:

```python
from miAgente.service import handle_request_payload as mi_agente_handler


@https_fn.on_request()
def mi_agente_api(req: https_fn.Request) -> https_fn.Response:
    if req.method != "POST":
        return json_response({"ok": False, "error": "Method not allowed"}, status=405)

    payload = req.get_json(silent=True) or {}
    result = mi_agente_handler(payload)
    return json_response({"ok": True, "result": result})
```

## Cuándo usar una función directa y cuándo usar router

- Función directa:
  conviene cuando el agente tendrá un endpoint propio, estable y fácil de identificar.

- Router:
  conviene cuando varios agentes comparten una sola entrada HTTP y el body indica cuál ejecutar.

En este repositorio se dejaron ambos ejemplos para que el equipo elija según el caso.

## Qué documentar cuando un agente se expone por API

Además del README técnico del agente, se debe documentar:

- nombre de la función en Firebase,
- URL o nombre del endpoint,
- método HTTP,
- ejemplo de request,
- ejemplo de response,
- errores esperados,
- proyecto Firebase donde se despliega,
- credencial o ambiente que utiliza.

## Recomendaciones importantes para `main.py`

- No hardcodear API keys.
- No hardcodear secretos de producción.
- Mantener `main.py` como capa de entrada, no como lugar principal de lógica del negocio.
- Si el agente crece mucho, dejar la mayor parte del trabajo en `service.py` y `pipeline.py`.
- Si se usan varios ambientes, dejar claro qué llave usa cada uno.
- Si un agente escribe en Firestore o Storage, documentarlo en su README.

Ejemplo de body para `agent_base_api`:

```json
{
  "message": "Hola agente",
  "metadata": {
    "source": "firebase"
  }
}
```

Ejemplo de body para `example_agent_router`:

```json
{
  "agent": "agentBaseMediprocesos",
  "message": "Hola agente",
  "metadata": {
    "source": "firebase-router"
  }
}
```

## Recomendación para exponer agentes por API

- Si el agente tendrá uso estable e independiente, crear una función propia.
- Si se quiere centralizar varios agentes, usar un router.
- Cada vez que se agregue un agente nuevo, documentar en su README:
  - nombre del endpoint,
  - método HTTP,
  - estructura del request,
  - estructura del response,
  - ambiente donde se despliega.

## Ambientes Firebase

Se dejó la carpeta `functions/script/keys/` con placeholders para credenciales por ambiente:

- `firebase-sa.json`
- `firebase-sa-staging.json`
- `firebase-sa-prod.json`

Uso sugerido:

- `firebase-sa.json`: credencial base o local.
- `firebase-sa-staging.json`: ambiente staging.
- `firebase-sa-prod.json`: producción.

## Proyectos Firebase soportados

Según la referencia encontrada en `Alizia`, los proyectos usados son:

- `edge-001`
- `edge-prod-002`

Nota importante:
En tu mensaje mencionaste `edge-prod--02`, pero en `Alizia` la referencia real encontrada en scripts y llaves es `edge-prod-002`. Por consistencia, en este repositorio dejé documentado `edge-prod-002`. Si el equipo realmente usa otro ID distinto, solo hay que actualizar el README del agente y la configuración asociada.

## Recomendaciones para cada agente

- Mantener prompts, lógica y schemas separados.
- Validar siempre entrada y salida.
- Evitar mezclar secretos con código fuente.
- Documentar claramente de dónde toma datos y hacia dónde escribe resultados.
- Si usa Firebase, indicar colección, bucket, proyecto y credencial esperada.
- Si usa búsqueda web o herramientas adicionales, documentarlo.

## Qué revisar antes de dar por listo un agente

- Tiene `README.md` propio.
- Tiene entrada y salida definidas en `schemas.py`.
- No tiene API keys hardcodeadas.
- Puede ejecutarse localmente.
- Está claro en qué proyecto se usa.
- Está claro si usa `edge-001`, `edge-prod-002` o staging.
- Tiene ejemplo mínimo de ejecución.

## Referencias usadas

La estructura de esta base se apoyó en:

- `/Users/desarrollomp/Documents/MEDIPROCESOS-PRO/Alizia/functions/agentATCFinalSync`
- `/Users/desarrollomp/Documents/MEDIPROCESOS-PRO/Alizia/functions/agentFinalPertinenciaV4`
