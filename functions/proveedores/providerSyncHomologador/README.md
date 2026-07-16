# providerSyncHomologador

Agente para Provider Sync que recibe un archivo Excel o CSV con catalogos de servicios de proveedores y devuelve un JSON homologado.

## Objetivo

Este agente analiza filas con servicios de laboratorio, radiologia, hospitalarios y similares para proponer:

- codigo Medical FIIS principal,
- nombre estandar internacional del servicio,
- codigos candidatos alternos,
- observaciones y nivel de confianza,
- marcas de revision humana cuando exista ambiguedad.

El agente puede apoyarse en busqueda web para validar sinonimos, nombres tecnicos y clasificaciones.

## Ubicacion

- Carpeta: `functions/proveedores/providerSyncHomologador`

## Formatos de entrada soportados

- `rows`: lista JSON de filas.
- `filePath`: ruta local a `.xlsx`, `.xlsm`, `.csv` o `.tsv`.
- `excelBase64`: archivo codificado en base64.
- `csvText`: texto CSV.

## Formato esperado por fila

```csv
"tipoServicio","codigoServicio","nombreServicio","moneda","precio","tipoProveedor","codigoProveedor","nombreProveedor"
2,"852201",FACTOR V DE LEYDEN,1,1473.21,6,127,TECNODIAGNOSIS
2,"80164",ACIDO VALPROICO/ANTIASMATICO,1,160.71,2,657,CENTRO MEDICO BETHESDA
2,"84703",SEROLOGIA HCG,1,44.64,2,644,HOSPITAL MONTE CRISTO
2,"86695",HERPES SIMPLE IGM,1,106.03,2,644,HOSPITAL MONTE CRISTO
```

## Respuesta

Devuelve un JSON con:

- metadatos del procesamiento,
- lista `items` homologados por fila,
- `resumen` agregado.

## Ejemplo de uso local

```bash
cd /Users/desarrollomp/Documents/MEDIPROCESOS-PRO/AGENTES_MEDI/functions/proveedores/providerSyncHomologador
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY="sk-..."
python3 pipeline.py '{"filePath":"/tmp/catalogo_proveedor.xlsx","enableWebSearch":true}'
```

## Notas operativas

- Si el agente no puede confirmar la equivalencia exacta, dejara `codigoMedicalFiis` en `null`.
- En casos ambiguos, llenara `codigosCandidatos` y activara `requiereRevisionHumana`.
- La calidad final depende de contar con un catalogo oficial o maestro de codigos Medical FIIS. Si ese catalogo existe luego, conviene conectarlo como fuente primaria para subir precision.
