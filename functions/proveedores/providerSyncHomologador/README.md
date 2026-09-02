# providerSyncHomologador

Agente HTTP de Firebase para homologar catalogos de laboratorios y diagnostico de
ProviderSync/LabSync.

## Flujo

1. ProviderSync extrae las filas de un Excel, CSV o TXT.
2. Envia las filas, el catalogo vigente de `CPT_PRODUCT` y el catalogo `SERVICE_TYPE`.
3. El agente recupera candidatos del catalogo interno y del archivo
   `CODIGO MEDICAL FEES.xlsx`.
4. Ejecuta una primera homologacion sin cargar el PDF.
5. Solo las filas sin asociacion o con confianza menor a `80` se procesan nuevamente
   con candidatos de `MEDICAL-FEES-DATA.pdf`.
6. El modelo decide la asociacion y el Tipo de Servicio usando unicamente candidatos
   verificados.
7. La respuesta conserva una fila por registro y agrega fuente, categoria, confianza
   y revision humana.

Los lotes de una misma etapa se consultan en paralelo con una concurrencia maxima
de `3`. El fallback PDF comienza despues de completar y validar la etapa inicial.

La prioridad es:

1. `catalogo_cpt`
2. `medical_fees` desde Excel
3. `medical_fees` desde PDF, solo como fallback
4. `sin_coincidencia`

## Endpoint

Firebase Function:

```text
provider_sync_homologador_api
```

Metodo: `POST`

## Entrada

```json
{
  "fileName": "precios_raiza.xlsx",
  "rows": [
    {
      "rowNumber": 2,
      "precio": "Q200,00",
      "fechaInicio": "03/10/2025",
      "observaciones": "",
      "codigoServicio": "13.04.13",
      "nombreServicio": "MAXILAR INFERIOR O SUPERIOR",
      "codigoProveedor": "RAIZA",
      "nombreProveedor": "RAIZA"
    }
  ],
  "catalogoCpt": [
    {
      "idCptProduct": 99,
      "codigoCpt": "70100",
      "nombreCpt": "RAYOS X DE MANDIBULA, MENOS DE 4 VISTAS",
      "tipoProcedimientoId": 4,
      "tipoProcedimientoNombre": "Radiologia",
      "tipoCptId": 2,
      "tipoCptNombre": "IMAGENOLOGIA",
      "estado": 1
    }
  ],
  "catalogoTiposServicio": [
    {
      "idTipoServicio": 7,
      "nombreTipoServicio": "Rayos X",
      "abreviatura": "RX"
    }
  ],
  "batchSize": 15,
  "maxCandidates": 5,
  "enableWebSearch": false
}
```

Tambien se aceptan `filePath`, `excelBase64` y `csvText` para pruebas o integraciones
alternas. Los formatos soportados son `.xlsx`, `.xlsm`, `.csv`, `.tsv` y `.txt`.

El catalogo `catalogoTiposServicio` acepta tanto el contrato del API
(`idTipoServicio`, `nombreTipoServicio`) como las columnas directas de base de datos
(`ID_SERVICE_TYPE`, `DESCRIPTION`).

Para los CPT registrados, `tipoCptId` y `tipoCptNombre` identifican la
clasificacion de `CPT_PRODUCT.ID_CPT`. El homologador incorpora el nombre del tipo
en la recuperacion de candidatos y exige compatibilidad semantica con el servicio
recibido. Una semejanza lexical no habilita asociaciones entre ambitos distintos,
como laboratorio y hospitalizacion.

Encabezados reconocidos incluyen:

- `PRECIO NEGOCIADO`
- `FECHA DE INICIO`
- `OBSERVACIONES`
- `CODIGO ASIGNADO RAIZA`
- `NOMBRE ASIGNADO RAIZA`
- `CODIGO PROCEDIMIENTO`
- `NOMBRE PROCEDIMIENTO`

## Respuesta por fila

```json
{
  "rowNumber": 2,
  "codigoServicio": "13.04.13",
  "nombreServicioOriginal": "MAXILAR INFERIOR O SUPERIOR",
  "precio": "Q200,00",
  "fechaInicio": "03/10/2025",
  "estadoAsociacion": "asociado",
  "fuenteAsociacion": "catalogo_cpt",
  "idCptProduct": 99,
  "codigoCpt": "70100",
  "nombreCpt": "RAYOS X DE MANDIBULA, MENOS DE 4 VISTAS",
  "nombreCptOriginal": "Radiologic examination, mandible; partial, less than 4 views",
  "codigoMedicalFees": "70100",
  "categoria": "RX",
  "tipoCptId": 2,
  "tipoCptNombre": "IMAGENOLOGIA",
  "tipoServicioId": 7,
  "tipoServicioNombre": "Rayos X",
  "confianzaPorcentaje": 93,
  "confianza": "alta",
  "requiereRevisionHumana": false,
  "motivo": "Coinciden anatomia y alcance radiologico.",
  "codigosCandidatos": []
}
```

Valores de `estadoAsociacion`:

- `asociado`: existe en el catalogo CPT recibido.
- `cpt_nuevo_sugerido`: existe en Medical Fees, pero no en el catalogo actual.
- `sin_asociacion`: no hay evidencia suficiente.

`itemsParaRevision` cuenta exclusivamente registros con `confianzaPorcentaje`
menor a `80`. Cuando la fuente es `medical_fees`, `nombreCptOriginal` conserva el
texto verificado. Si el codigo proviene del Excel, `categoria` contiene el nombre
exacto de la pestaña y `paginaMedicalFees` es nulo. Si proviene del PDF,
`categoria` es nulo, `paginaMedicalFees` contiene la pagina y `nombreCpt` incluye
la traduccion al espanol.

Dentro de `codigosCandidatos`, los candidatos de `medical_fees` utilizan `nombre`
para la traduccion al espanol y `nombreOriginal` para el texto exacto del libro.
La lista contiene como maximo `5` opciones, ordenadas por `scorePreliminar`, y no
incluye candidatos con una coincidencia menor a `45`.

## Excel Medical Fees

La ruta por defecto se resuelve en este orden:

```text
functions/proveedores/providerSyncHomologador/CODIGO_MEDICAL_FEES.xlsx
functions/proveedores/providerSyncHomologador/CODIGO MEDICAL FEES.xlsx
```

El Excel se indexa una vez por instancia de Firebase. Cada pestaña se conserva
como `categoria`. Se puede cambiar la ruta con `MEDICAL_FEES_EXCEL_PATH`.

## PDF Medical Fees

La ruta por defecto es:

```text
functions/proveedores/providerSyncHomologador/MEDICAL-FEES-DATA.pdf
```

El PDF se carga e indexa de forma diferida, solo si alguna fila queda sin asociacion
o con confianza menor a `80` despues de la primera pasada con el Excel. El indice
se mantiene en memoria y su ruta se puede cambiar con `MEDICAL_FEES_PDF_PATH`.

## Variables

```text
OPENAI_API_KEY
PROVIDER_SYNC_HOMOLOGADOR_MODEL
PROVIDER_SYNC_HOMOLOGADOR_SERVICE_TIER
PROVIDER_SYNC_HOMOLOGADOR_MAX_CONCURRENCY
MEDICAL_FEES_PDF_PATH
MEDICAL_FEES_EXCEL_PATH
```

`PROVIDER_SYNC_HOMOLOGADOR_MODEL` es opcional.
`PROVIDER_SYNC_HOMOLOGADOR_SERVICE_TIER` utiliza `priority` por defecto para
reducir la latencia de las llamadas a OpenAI. Puede cambiarse a `auto` o
`default` si el proyecto asociado a la API key no debe utilizar procesamiento
prioritario.
`PROVIDER_SYNC_HOMOLOGADOR_MAX_CONCURRENCY` acepta valores de `1` a `5` y utiliza
`3` por defecto. El valor `1` conserva la ejecucion secuencial.

Para desarrollo local se puede crear `functions/.secret.local` usando
`functions/.secret.local.example` como referencia. El archivo real esta ignorado
por Git y tambien es utilizado por el emulador de Firebase.

Para produccion, registra la llave en Firebase Secret Manager:

```bash
firebase functions:secrets:set OPENAI_API_KEY --project ID_PROYECTO
```

## Pruebas

```bash
PYTHONPATH=functions python3 -m unittest discover \
  -s functions/proveedores/providerSyncHomologador/tests -v
```

## Validacion manual

Desde la raiz de `AGENTES_MEDI`, valida primero el indice y las categorias del
Excel. El modo diagnostico agrega candidatos del PDF solo cuando el mejor candidato
Excel tiene puntaje preliminar menor a `80`, sin consumir OpenAI:

```bash
PYTHONPATH=functions python3 \
  functions/proveedores/providerSyncHomologador/run_manual_cases.py \
  --mode index
```

Ejecuta el pipeline completo con OpenAI:

```bash
export OPENAI_API_KEY="..."
PYTHONPATH=functions python3 \
  functions/proveedores/providerSyncHomologador/run_manual_cases.py \
  --mode direct
```

Para usar un payload propio agrega `--payload /ruta/request.json`.

## Emulador Firebase

```bash
python3.13 -m venv functions/venv
source functions/venv/bin/activate
python -m pip install -r functions/requirements.txt
export OPENAI_API_KEY="..."
firebase emulators:start --only functions --project demo-agentes-medi
```

En otra terminal:

```bash
source functions/venv/bin/activate
PYTHONPATH=functions python3 \
  functions/proveedores/providerSyncHomologador/run_manual_cases.py \
  --mode http
```
