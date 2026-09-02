import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from proveedores.providerSyncHomologador.medical_fees_excel import (
    load_medical_fees_excel_index,
)
from proveedores.providerSyncHomologador.matching import TextCandidateIndex

from .prompts import SYSTEM_PROMPT, USER_PROMPT
from .schemas import (
    DoctorPlusAgentData,
    DoctorPlusAgentInput,
    DoctorPlusAgentResponse,
    DoctorPlusHomologatedItem,
    DoctorPlusPriceRow,
    DoctorPlusSummary,
    MedicalFeesCandidate,
)


MODEL_NAME = os.getenv(
    "PROVIDER_SYNC_DOCTOR_PLUS_PRICES_MODEL",
    os.getenv("PROVIDER_SYNC_HOMOLOGADOR_MODEL", "gpt-5.6-luna"),
)
OPENAI_SERVICE_TIER = (
    os.getenv("PROVIDER_SYNC_DOCTOR_PLUS_PRICES_SERVICE_TIER", "priority")
    .strip()
    .lower()
    or "priority"
)
MAX_CONCURRENCY = max(
    1,
    min(5, int(os.getenv("PROVIDER_SYNC_DOCTOR_PLUS_PRICES_MAX_CONCURRENCY", "3"))),
)
MIN_CANDIDATE_SCORE = 35


def build_client() -> Any:
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("No se encontro OPENAI_API_KEY en variables de entorno.")
    return OpenAI(api_key=api_key)


def extract_json(output_text: str) -> dict[str, Any]:
    cleaned = (output_text or "").strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = lines[1:] if lines and lines[0].startswith("```") else lines
        lines = lines[:-1] if lines and lines[-1].strip() == "```" else lines
        cleaned = "\n".join(lines).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("El agente no devolvio JSON valido.")
    return json.loads(cleaned[start:end + 1])


def batch_rows(rows: list[DoctorPlusPriceRow], size: int) -> list[list[DoctorPlusPriceRow]]:
    return [rows[index:index + size] for index in range(0, len(rows), size)]


def candidate_models(candidates: list[dict[str, Any]]) -> list[MedicalFeesCandidate]:
    return [
        MedicalFeesCandidate(
            codigo=str(candidate["codigo"]),
            nombre=str(candidate["nombre"]),
            categoria=candidate.get("categoria"),
            scorePreliminar=int(candidate.get("scorePreliminar") or 0),
        )
        for candidate in candidates
        if int(candidate.get("scorePreliminar") or 0) >= MIN_CANDIDATE_SCORE
    ]


def fallback_item(
    row: DoctorPlusPriceRow,
    candidates: list[dict[str, Any]],
    reason: str,
) -> DoctorPlusHomologatedItem:
    return DoctorPlusHomologatedItem(
        rowNumber=row.rowNumber,
        codigoServicioOmega=row.codigoServicio,
        nombreServicioOriginal=row.nombreServicio,
        estadoAsociacion="sin_asociacion",
        confianzaPorcentaje=0,
        requiereRevisionHumana=True,
        motivo=reason,
        candidatos=candidate_models(candidates),
    )


def normalize_item(
    raw_item: dict[str, Any],
    row: DoctorPlusPriceRow,
    candidates: list[dict[str, Any]],
) -> DoctorPlusHomologatedItem:
    try:
        confidence = int(float(str(raw_item.get("confianzaPorcentaje", 0))))
    except (TypeError, ValueError):
        confidence = 0
    confidence = max(0, min(100, confidence))
    selected_code = str(raw_item.get("codigoProviderSync") or "").strip()
    selected = next(
        (
            candidate
            for candidate in candidates
            if str(candidate.get("codigo") or "").strip() == selected_code
        ),
        None,
    )
    if raw_item.get("estadoAsociacion") != "asociado" or selected is None:
        return fallback_item(
            row,
            candidates,
            str(raw_item.get("motivo") or "No se encontro una coincidencia verificada."),
        )
    return DoctorPlusHomologatedItem(
        rowNumber=row.rowNumber,
        codigoServicioOmega=row.codigoServicio,
        nombreServicioOriginal=row.nombreServicio,
        estadoAsociacion="asociado",
        codigoProviderSync=str(selected["codigo"]),
        nombreMedicalFees=str(selected["nombre"]),
        categoriaMedicalFees=selected.get("categoria"),
        confianzaPorcentaje=confidence,
        requiereRevisionHumana=confidence < 80,
        motivo=str(raw_item.get("motivo") or "Coincidencia verificada en Medical Fees Excel."),
        candidatos=candidate_models(candidates),
    )


def run_batch(
    rows: list[DoctorPlusPriceRow],
    index: TextCandidateIndex,
    max_candidates: int,
    client: Any,
) -> tuple[list[DoctorPlusHomologatedItem], int]:
    enriched_rows: list[dict[str, Any]] = []
    candidates_by_row: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        candidates = index.search(row.codigoServicio, row.nombreServicio, max_candidates)
        candidates_by_row[row.rowNumber] = candidates
        enriched_rows.append(
            {
                "rowNumber": row.rowNumber,
                "codigoServicio": row.codigoServicio,
                "nombreServicio": row.nombreServicio,
                "candidatosMedicalFeesExcel": candidates,
            }
        )

    prompt = USER_PROMPT.format(
        context_json=json.dumps(
            {
                "fuentePermitida": "CODIGO MEDICAL FEES.xlsx",
                "totalFilas": len(rows),
                "catalogoCptRecibido": False,
                "pdfCargado": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        rows_json=json.dumps(enriched_rows, ensure_ascii=False, indent=2),
    )
    response = client.responses.create(
        model=MODEL_NAME,
        service_tier=OPENAI_SERVICE_TIER,
        reasoning={"effort": "medium"},
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    parsed = extract_json(response.output_text)
    raw_by_row = {
        int(item.get("rowNumber")): item
        for item in parsed.get("items", [])
        if isinstance(item, dict) and item.get("rowNumber") is not None
    }
    items = [
        normalize_item(
            raw_by_row.get(row.rowNumber, {}),
            row,
            candidates_by_row[row.rowNumber],
        )
        for row in rows
    ]
    tokens = getattr(getattr(response, "usage", None), "total_tokens", None) or 0
    return items, int(tokens)


def process_request_payload(
    raw_payload: dict[str, Any],
    client: Optional[Any] = None,
    medical_fees_excel_index: Optional[TextCandidateIndex] = None,
) -> DoctorPlusAgentResponse:
    started = time.monotonic()
    payload = DoctorPlusAgentInput.model_validate(raw_payload)
    index = medical_fees_excel_index or load_medical_fees_excel_index()
    selected_client = client or build_client()
    batches = batch_rows(payload.rows, payload.batchSize)
    items: list[DoctorPlusHomologatedItem] = []
    total_tokens = 0

    if len(batches) == 1 or MAX_CONCURRENCY == 1:
        results = [
            run_batch(batch, index, payload.maxCandidates, selected_client)
            for batch in batches
        ]
    else:
        results = []
        with ThreadPoolExecutor(max_workers=min(MAX_CONCURRENCY, len(batches))) as executor:
            futures = [
                executor.submit(
                    run_batch,
                    batch,
                    index,
                    payload.maxCandidates,
                    selected_client,
                )
                for batch in batches
            ]
            for future in as_completed(futures):
                results.append(future.result())

    for batch_items, tokens in results:
        items.extend(batch_items)
        total_tokens += tokens
    items.sort(key=lambda item: item.rowNumber)

    summary = DoctorPlusSummary(
        totalItems=len(items),
        itemsAsociados=sum(1 for item in items if item.estadoAsociacion == "asociado"),
        itemsSinAsociacion=sum(1 for item in items if item.estadoAsociacion == "sin_asociacion"),
        itemsParaRevision=sum(1 for item in items if item.requiereRevisionHumana),
    )
    return DoctorPlusAgentResponse(
        modelo=MODEL_NAME,
        tokensUsados=total_tokens or None,
        tiempoRespuestaSegundos=f"{time.monotonic() - started:.6f}",
        data=DoctorPlusAgentData(
            totalFilasEntrada=len(payload.rows),
            items=items,
            resumen=summary,
        ),
    )
