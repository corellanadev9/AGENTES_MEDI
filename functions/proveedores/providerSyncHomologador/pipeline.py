import base64
import csv
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional
from zipfile import BadZipFile

from openai import OpenAI
from openpyxl import load_workbook

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

try:
    from .prompts import SYSTEM_PROMPT, USER_PROMPT
    from .schemas import AgentData, AgentInput, AgentResponse, HomologatedItem, ProcessingSummary, ServiceRow
except ImportError:
    from prompts import SYSTEM_PROMPT, USER_PROMPT
    from schemas import AgentData, AgentInput, AgentResponse, HomologatedItem, ProcessingSummary, ServiceRow


MODEL_NAME = "gpt-5.4-mini"
SUPPORTED_FILE_SUFFIXES = {".xlsx", ".xlsm", ".csv", ".tsv"}
EXPECTED_COLUMNS = [
    "tipoServicio",
    "codigoServicio",
    "nombreServicio",
    "moneda",
    "precio",
    "tipoProveedor",
    "codigoProveedor",
    "nombreProveedor",
]


def build_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("No se encontro OPENAI_API_KEY en variables de entorno.")
    return OpenAI(api_key=api_key)


def normalize_header(value: Any) -> str:
    return str(value or "").strip()


def normalize_row_keys(row: dict[str, Any], row_number: int) -> dict[str, Any]:
    normalized = {normalize_header(key): value for key, value in row.items()}
    normalized["rowNumber"] = normalized.get("rowNumber") or row_number
    return normalized


def load_rows_from_delimited_text(text: str, delimiter: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(reader, start=1):
        rows.append(normalize_row_keys(row, idx))
    return rows


def load_rows_from_excel_bytes(file_bytes: bytes) -> list[dict[str, Any]]:
    workbook = load_workbook(filename=io.BytesIO(file_bytes), read_only=True, data_only=True)
    sheet = workbook.active
    header_cells = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), None)
    if not header_cells:
        return []

    headers = [normalize_header(cell) for cell in header_cells]
    rows: list[dict[str, Any]] = []
    for sheet_row_number, values in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        item = {headers[index]: values[index] for index in range(len(headers))}
        if any(value not in (None, "") for value in item.values()):
            rows.append(normalize_row_keys(item, sheet_row_number))
    return rows


def load_rows_from_file(file_path: str) -> list[dict[str, Any]]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo: {file_path}")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_FILE_SUFFIXES:
        raise ValueError(
            f"Formato no soportado: {suffix}. Usa uno de {sorted(SUPPORTED_FILE_SUFFIXES)}."
        )

    if suffix in {".csv", ".tsv"}:
        delimiter = "," if suffix == ".csv" else "\t"
        return load_rows_from_delimited_text(path.read_text(encoding="utf-8-sig"), delimiter)

    return load_rows_from_excel_bytes(path.read_bytes())


def decode_base64_file(payload: AgentInput) -> list[dict[str, Any]]:
    if not payload.excelBase64:
        return []

    try:
        file_bytes = base64.b64decode(payload.excelBase64)
    except Exception as exc:
        raise ValueError("excelBase64 no contiene un archivo valido en base64.") from exc

    file_name = (payload.fileName or "").lower()
    if file_name.endswith(".csv"):
        return load_rows_from_delimited_text(file_bytes.decode("utf-8-sig"), ",")
    if file_name.endswith(".tsv"):
        return load_rows_from_delimited_text(file_bytes.decode("utf-8-sig"), "\t")

    try:
        return load_rows_from_excel_bytes(file_bytes)
    except BadZipFile as exc:
        raise ValueError(
            "No se pudo leer el archivo base64 como Excel. Si es CSV, envia fileName con extension .csv."
        ) from exc


def collect_rows(payload: AgentInput) -> list[ServiceRow]:
    raw_rows: list[dict[str, Any]] = []

    if payload.rows:
        raw_rows.extend([row.model_dump(mode="json", exclude_none=True) for row in payload.rows])
    if payload.filePath:
        raw_rows.extend(load_rows_from_file(payload.filePath))
    if payload.csvText:
        raw_rows.extend(load_rows_from_delimited_text(payload.csvText, ","))
    if payload.excelBase64:
        raw_rows.extend(decode_base64_file(payload))

    if not raw_rows:
        raise ValueError("No se encontraron filas para procesar.")

    validated_rows: list[ServiceRow] = []
    for idx, row in enumerate(raw_rows, start=1):
        normalized = normalize_row_keys(row, idx)
        validated_rows.append(ServiceRow.model_validate(normalized))
    return validated_rows


def batch_rows(rows: list[ServiceRow], batch_size: int) -> list[list[ServiceRow]]:
    return [rows[index:index + batch_size] for index in range(0, len(rows), batch_size)]


def build_context(payload: AgentInput, rows: list[ServiceRow]) -> dict[str, Any]:
    first = rows[0]
    return {
        "archivo": payload.fileName or payload.filePath,
        "columnasEsperadas": EXPECTED_COLUMNS,
        "totalFilas": len(rows),
        "tipoProveedor": first.tipoProveedor,
        "codigoProveedor": first.codigoProveedor,
        "nombreProveedor": first.nombreProveedor,
        "metadata": payload.metadata or {},
        "instruccionesNegocio": [
            "codigoServicio es el codigo interno actual de Mediprocesos.",
            "Se debe proponer un codigo Medical FIIS estandar cuando sea posible.",
            "Tambien se debe devolver el nombre estandar internacional del servicio.",
            "Listar codigos candidatos si existe ambiguedad o multiples equivalencias razonables.",
        ],
    }


def extract_json_from_text(output_text: str) -> dict[str, Any]:
    cleaned = output_text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("El modelo no devolvio un objeto JSON valido.")
    return json.loads(cleaned[start:end + 1])


def run_agent_for_batch(
    batch: list[ServiceRow],
    context: dict[str, Any],
    client: OpenAI,
    enable_web_search: bool,
) -> tuple[list[HomologatedItem], Optional[int]]:
    rendered_prompt = USER_PROMPT.format(
        context_json=json.dumps(context, ensure_ascii=False, indent=2),
        rows_json=json.dumps(
            [row.model_dump(mode="json", exclude_none=True) for row in batch],
            ensure_ascii=False,
            indent=2,
        ),
    )

    request_args: dict[str, Any] = {
        "model": MODEL_NAME,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": rendered_prompt},
        ],
    }
    if enable_web_search:
        request_args["tools"] = [{"type": "web_search_preview"}]

    response = client.responses.create(**request_args)
    parsed = extract_json_from_text((response.output_text or "").strip())
    items = [HomologatedItem.model_validate(item) for item in parsed.get("items", [])]
    total_tokens = getattr(getattr(response, "usage", None), "total_tokens", None)
    return items, total_tokens


def process_request_payload(
    raw_payload: dict[str, Any],
    client: Optional[OpenAI] = None,
) -> AgentResponse:
    started = time.monotonic()
    payload = AgentInput.model_validate(raw_payload)
    rows = collect_rows(payload)
    context = build_context(payload, rows)

    if client is None:
        client = build_client()

    homologated_items: list[HomologatedItem] = []
    total_tokens = 0

    for batch in batch_rows(rows, payload.batchSize):
        items, batch_tokens = run_agent_for_batch(
            batch=batch,
            context=context,
            client=client,
            enable_web_search=payload.enableWebSearch,
        )
        homologated_items.extend(items)
        if batch_tokens:
            total_tokens += batch_tokens

    result_by_row = {item.rowNumber: item for item in homologated_items}
    ordered_items: list[HomologatedItem] = []
    for index, row in enumerate(rows, start=1):
        row_number = row.rowNumber or index
        if row_number in result_by_row:
            ordered_items.append(result_by_row[row_number])
            continue

        ordered_items.append(
            HomologatedItem(
                rowNumber=row_number,
                codigoServicio=str(row.codigoServicio),
                nombreServicioOriginal=row.nombreServicio,
                nombreServicioEstandar=None,
                categoriaEstandar=None,
                codigoMedicalFiis=None,
                confianza="baja",
                requiereRevisionHumana=True,
                codigosCandidatos=[],
                fuentesWeb=[],
                observaciones="El modelo no devolvio homologacion para esta fila.",
            )
        )

    elapsed = f"{(time.monotonic() - started):.6f}"
    summary = ProcessingSummary(
        totalItems=len(ordered_items),
        itemsConCodigoPrincipal=sum(1 for item in ordered_items if item.codigoMedicalFiis),
        itemsParaRevision=sum(1 for item in ordered_items if item.requiereRevisionHumana),
    )

    first_row = rows[0]
    data = AgentData(
        proveedor=first_row.nombreProveedor,
        tipoProveedor=str(first_row.tipoProveedor) if first_row.tipoProveedor is not None else None,
        archivoProcesado=payload.fileName or payload.filePath,
        totalFilasEntrada=len(rows),
        items=ordered_items,
        resumen=summary,
    )
    return AgentResponse(
        modelo=MODEL_NAME,
        tokensUsados=total_tokens or None,
        tiempoRespuestaSegundos=elapsed,
        data=data,
    )


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            'Uso: python3 pipeline.py \'{"filePath":"/ruta/catalogo.xlsx","metadata":{"source":"local"}}\''
        )

    payload = json.loads(sys.argv[1])
    result = process_request_payload(payload)
    print(json.dumps(result.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

