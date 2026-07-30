import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

try:
    from .medical_fees import load_medical_fees_index, load_medical_fees_records
    from .medical_fees_excel import (
        load_medical_fees_excel_index,
        load_medical_fees_excel_records,
    )
    from .pipeline import process_request_payload
except ImportError:
    from medical_fees import load_medical_fees_index, load_medical_fees_records
    from medical_fees_excel import (
        load_medical_fees_excel_index,
        load_medical_fees_excel_records,
    )
    from pipeline import process_request_payload


DEFAULT_EMULATOR_URL = (
    "http://127.0.0.1:5001/demo-agentes-medi/us-central1/"
    "provider_sync_homologador_api"
)
DEFAULT_SERVICE_TYPES_PATH = (
    Path(__file__).resolve().parent / "service_types_provider_sync.json"
)
LOCAL_SECRET_PATH = Path(__file__).resolve().parents[2] / ".secret.local"

SAMPLE_ROWS = [
    ("13.04.13", "MAXILAR INFERIOR O SUPERIOR", "Q200,00"),
    ("13.04.61", "MANDIBULA 3 VISTAS", "Q200,00"),
    ("13.04.17", "RX DE OIDOS", "Q200,00"),
    ("13.04.16", "MASTOIDES", "Q200,00"),
    ("13.04.19", "ARCO CIGOMATICO", "Q200,00"),
    ("13.04.20", "ORBITAS", "Q200,00"),
    ("13.04.15", "HUESOS NARIZ", "Q200,00"),
    ("13,04", "SENOS PARANASALES", "Q285,00"),
]


def sample_payload() -> dict[str, Any]:
    rows = []
    for row_number, (code, name, price) in enumerate(SAMPLE_ROWS, start=2):
        rows.append(
            {
                "rowNumber": row_number,
                "precio": price,
                "fechaInicio": "03/10/2025",
                "observaciones": "",
                "codigoServicio": code,
                "nombreServicio": name,
                "codigoProveedor": "RAIZA",
                "nombreProveedor": "RAIZA",
            }
        )

    return {
        "fileName": "precios_raiza_prueba.xlsx",
        "rows": rows,
        "catalogoCpt": [
            {
                "idCptProduct": 1001,
                "codigoCpt": "70100",
                "nombreCpt": "RAYOS X DE MANDIBULA, MENOS DE 4 VISTAS",
                "tipoProcedimientoNombre": "Radiologia",
                "estado": 1,
            },
            {
                "idCptProduct": 1002,
                "codigoCpt": "70120",
                "nombreCpt": "RAYOS X DE MASTOIDES, HASTA 3 PROYECCIONES",
                "tipoProcedimientoNombre": "Radiologia",
                "estado": 1,
            },
            {
                "idCptProduct": 1003,
                "codigoCpt": "70200",
                "nombreCpt": "RAYOS X DE ORBITAS, MINIMO 4 VISTAS",
                "tipoProcedimientoNombre": "Radiologia",
                "estado": 1,
            },
            {
                "idCptProduct": 1004,
                "codigoCpt": "70160",
                "nombreCpt": "RAYOS X DE HUESOS NASALES",
                "tipoProcedimientoNombre": "Radiologia",
                "estado": 1,
            },
        ],
        "catalogoTiposServicio": json.loads(
            DEFAULT_SERVICE_TYPES_PATH.read_text(encoding="utf-8")
        ),
        "batchSize": 15,
        "maxCandidates": 5,
        "enableWebSearch": False,
    }


def load_payload(payload_path: str | None) -> dict[str, Any]:
    if not payload_path:
        return sample_payload()
    return json.loads(Path(payload_path).read_text(encoding="utf-8"))


def load_local_secrets() -> None:
    if not LOCAL_SECRET_PATH.exists():
        return
    for raw_line in LOCAL_SECRET_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def validate_index(payload: dict[str, Any]) -> dict[str, Any]:
    excel_index = load_medical_fees_excel_index()
    pdf_index = None
    results = []
    for row in payload.get("rows", []):
        excel_candidates = excel_index.search(
            row.get("codigoServicio"),
            row.get("nombreServicio"),
            limit=3,
        )
        requires_pdf = (
            not excel_candidates
            or excel_candidates[0].get("scorePreliminar", 0) < 80
        )
        pdf_candidates = []
        if requires_pdf:
            pdf_index = pdf_index or load_medical_fees_index()
            pdf_candidates = pdf_index.search(
                row.get("codigoServicio"),
                row.get("nombreServicio"),
                limit=3,
            )
        results.append(
            {
                "rowNumber": row.get("rowNumber"),
                "codigoProveedor": row.get("codigoServicio"),
                "nombreProveedor": row.get("nombreServicio"),
                "candidatosMedicalFeesExcel": excel_candidates,
                "requiereFallbackPdfPreliminar": requires_pdf,
                "candidatosMedicalFeesPdf": pdf_candidates,
            }
        )
    return {
        "ok": True,
        "mode": "index",
        "medicalFeesExcelRecords": len(load_medical_fees_excel_records()),
        "medicalFeesPdfRecords": (
            len(load_medical_fees_records()) if pdf_index is not None else 0
        ),
        "items": results,
    }


def run_direct(payload: dict[str, Any]) -> dict[str, Any]:
    result = process_request_payload(payload)
    return result.model_dump(mode="json", exclude_none=True)


def run_http(payload: dict[str, Any], url: str) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=300) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    load_local_secrets()
    parser = argparse.ArgumentParser(
        description="Valida manualmente el agente providerSyncHomologador."
    )
    parser.add_argument(
        "--mode",
        choices=("index", "direct", "http"),
        default="index",
        help="index no usa OpenAI; direct usa el pipeline; http prueba Firebase.",
    )
    parser.add_argument(
        "--payload",
        help="Ruta opcional a un JSON. Si se omite usa las ocho filas RAIZA.",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_EMULATOR_URL,
        help="URL para el modo http.",
    )
    args = parser.parse_args()

    payload = load_payload(args.payload)
    if args.mode == "index":
        result = validate_index(payload)
    elif args.mode == "direct":
        result = run_direct(payload)
    else:
        result = run_http(payload, args.url)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
