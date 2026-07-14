# agentBaseMediprocesos

Plantilla base para nuevos agentes de Mediprocesos.

Esta plantilla existe para que los agentes futuros de `AGENTES_MEDI` nazcan con una estructura uniforme y documentación mínima obligatoria.

## Estado

Plantilla inicial. Debe copiarse y personalizarse antes de usarse en un flujo real.

## Proyectos donde se usa

Pendiente de definir por el equipo.

Completar siempre esta sección con:

- proyecto o producto donde se consume,
- endpoint o proceso que lo llama,
- ambiente donde corre.

## Objetivo del agente

Describir aquí qué problema resuelve el agente y qué decisión o salida produce.

## Archivos incluidos

- `__init__.py`
  Marca la carpeta como paquete Python.

- `pipeline.py`
  Orquesta validación, prompt, llamada al modelo y respuesta final.

- `prompts.py`
  Contiene prompts del agente.

- `schemas.py`
  Define entrada y salida tipada con Pydantic.

- `service.py`
  Expone funciones simples para integrarlo desde otros servicios.

- `requirements.txt`
  Dependencias mínimas para ejecución local.

## Cómo usarlo

1. Renombrar la carpeta.
2. Ajustar `schemas.py`.
3. Ajustar `prompts.py`.
4. Completar la lógica de `pipeline.py`.
5. Actualizar este README con el caso real.

## Ejecución local

```bash
cd /Users/desarrollomp/Documents/MEDIPROCESOS-PRO/AGENTES_MEDI/functions/agentBaseMediprocesos
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY="sk-..."
python3 pipeline.py '{"message":"Hola agente","metadata":{"source":"local"}}'
```

## Ambientes relacionados

- `edge-001`
- `edge-prod-002`
- staging, si aplica

## Checklist antes de usar este agente

- Actualizar el nombre de la carpeta y del README.
- Documentar proyecto y consumo real.
- Verificar input y output.
- Confirmar ambiente Firebase objetivo.
- Confirmar que no existan secretos hardcodeados.
