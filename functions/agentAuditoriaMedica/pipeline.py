"""Proyección mínima, búsqueda clínica y normalización conservadora del dictamen."""

import json
import os
import re
import time
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from .config import load_local_env
from .prompts import RETRY_PROMPT, SYSTEM_PROMPT, USER_PROMPT
from .schemas import MODEL_AUDIT_SCHEMA, ModelAudit


MODEL_NAME = "gpt-6-luna"
ALLOWED_DOMAINS = (
    "fda.gov", "dailymed.nlm.nih.gov", "nih.gov", "cdc.gov", "who.int",
    "nice.org.uk", "ema.europa.eu", "acog.org", "cochranelibrary.com",
    "mspas.gob.gt", "atcddd.fhi.no",
)
CLINICAL_FIELDS = {
    "diagnosticos": ("codigoDiagnostico", "icd", "nombreDiagnostico"),
    "medicamentos": (
        "atc4", "atc5", "compuestoActivo", "descripcionMedicamento", "dosis",
        "duracion", "frecuencia", "unidadDuracion", "viaAdministracion",
        "concentracion", "cantidad",
    ),
}


def _project_rows(value: Any, fields: tuple[str, ...], label: str, limit: int) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError(f"{label} debe ser una lista de hasta {limit} elementos.")
    rows = []
    for index, row in enumerate(value, 1):
        if not isinstance(row, dict):
            raise ValueError(f"{label}[{index}] debe ser un objeto JSON.")
        projected = {}
        for field in fields:
            raw = row.get(field)
            if raw is None or raw == "":
                continue
            if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
                raise ValueError(f"{label}[{index}].{field} debe ser texto o número.")
            text = str(raw).strip()
            if len(text) > 500:
                raise ValueError(f"{label}[{index}].{field} excede 500 caracteres.")
            if text:
                projected[field] = text
        if not projected:
            raise ValueError(f"{label}[{index}] no contiene datos clínicos admitidos.")
        rows.append(projected)
    return rows


def _today_guatemala() -> date:
    return datetime.now(ZoneInfo("America/Guatemala")).date()


def _patient_age(data: dict[str, Any], reference_date: date | None = None) -> int:
    birth_raw = data.get("fechaNacimiento")
    if birth_raw:
        try:
            if not isinstance(birth_raw, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", birth_raw):
                raise ValueError
            birth = date.fromisoformat(birth_raw)
        except ValueError as exc:
            raise ValueError("fechaNacimiento debe tener formato AAAA-MM-DD.") from exc
        today = reference_date or _today_guatemala()
        age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
        if not 0 <= age <= 120:
            raise ValueError("fechaNacimiento debe ser anterior a la auditoría y dar una edad válida.")
        return age

    age_raw = data.get("edad")
    if isinstance(age_raw, bool) or not isinstance(age_raw, (int, str)):
        raise ValueError("Se requiere fechaNacimiento o edad para evaluar medicamentos.")
    age_text = str(age_raw).strip()
    if not age_text.isascii() or not age_text.isdecimal() or not 0 <= int(age_text) <= 120:
        raise ValueError("edad debe ser un número entero entre 0 y 120 años.")
    return int(age_text)


def project_clinical_data(raw_payload: dict[str, Any]) -> dict[str, Any]:
    """Envía al modelo solo edad clínica, diagnósticos y medicamentos."""
    if not isinstance(raw_payload, dict):
        raise ValueError("El cuerpo debe ser un objeto JSON.")
    data = raw_payload.get("data", raw_payload)
    if not isinstance(data, dict):
        raise ValueError("data debe ser un objeto JSON.")
    diagnoses = _project_rows(data.get("diagnosticos"), CLINICAL_FIELDS["diagnosticos"], "diagnosticos", 20)
    if not diagnoses:
        raise ValueError("Se requiere al menos un diagnóstico para auditar la pertinencia.")
    age = _patient_age(data)
    medicines = _project_rows(data.get("medicamentos"), CLINICAL_FIELDS["medicamentos"], "medicamentos", 20)
    if not medicines:
        raise ValueError("Se requiere al menos un medicamento para auditar la pertinencia.")
    items = [{"idItem": f"M{index}", "tipo": "medicamento", **row}
             for index, row in enumerate(medicines, 1)]
    return {"edad": age, "diagnosticos": diagnoses, "medicamentos": items}


def _canonical_url(url: str) -> str | None:
    try:
        cleaned = url.strip()
        markdown = re.fullmatch(r"\[[^\]]+\]\((https://[^\s)]+)\)", cleaned)
        parts = urlsplit(markdown.group(1) if markdown else cleaned)
        hostname = (parts.hostname or "").lower().rstrip(".")
        if parts.scheme.lower() != "https" or not hostname or parts.username or parts.password:
            return None
        if not any(hostname == domain or hostname.endswith("." + domain) for domain in ALLOWED_DOMAINS):
            return None
        query = urlencode([
            (key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
        ])
        return urlunsplit(("https", hostname, parts.path.rstrip("/") or "/", query, ""))
    except (TypeError, ValueError):
        return None


def _searched_sources(response: Any) -> tuple[bool, dict[str, dict[str, str]]]:
    output = response.model_dump().get("output", [])
    searched = False
    sources: dict[str, dict[str, str]] = {}
    for item in output:
        if item.get("type") == "web_search_call":
            searched = True
            for source in (item.get("action") or {}).get("sources") or []:
                url = source.get("url") if isinstance(source, dict) else None
                canonical = _canonical_url(url) if isinstance(url, str) else None
                if canonical:
                    sources[canonical] = {"titulo": source.get("title") or "Fuente clínica", "url": canonical}
        if item.get("type") == "message":
            for content in item.get("content") or []:
                for citation in content.get("annotations") or []:
                    if citation.get("type") != "url_citation":
                        continue
                    url = citation.get("url")
                    canonical = _canonical_url(url) if isinstance(url, str) else None
                    if canonical:
                        sources[canonical] = {"titulo": citation.get("title") or "Fuente clínica", "url": canonical}
    return searched, sources


def build_client() -> Any:
    from openai import OpenAI

    load_local_env()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("No se configuró OPENAI_API_KEY.")
    return OpenAI(api_key=api_key, timeout=180.0, max_retries=0)


def _empty_finding(item: dict[str, str], reason: str) -> dict[str, Any]:
    return {
        "idItem": item["idItem"], "tipo": item["tipo"], "descripcion": _item_description(item),
        "juicio": "insuficiente", "prioridad": "ninguna", "fundamentoClinico": reason,
        "informacionFaltante": ["Fuente clínica verificable para este medicamento."],
        "fuentes": [], "requiereRevisionClinicaAdicional": True,
    }


def _item_description(item: dict[str, str]) -> str:
    for key in ("descripcionMedicamento", "compuestoActivo", "atc5"):
        if item.get(key):
            return item[key]
    return "Medicamento sin descripción"


def _run_audit(
    client: Any, clinical_data: dict[str, Any], prompt: str,
    *, search_context_size: str = "medium", request_timeout: float | None = None,
) -> tuple[Any, dict[str, Any], bool, dict[str, dict[str, str]]]:
    request = {
        "model": MODEL_NAME,
        "reasoning": {"effort": "medium"},
        "text": {
            "verbosity": "medium",
            "format": {"type": "json_schema", "name": "auditoria_medica", "strict": True,
                       "schema": MODEL_AUDIT_SCHEMA},
        },
        "tools": [{"type": "web_search", "search_context_size": search_context_size,
                   "filters": {"allowed_domains": list(ALLOWED_DOMAINS)}}],
        "tool_choice": "required",
        "include": ["web_search_call.action.sources"],
        "store": False,
        "max_output_tokens": 10000,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt.format(
                clinical_json=json.dumps(clinical_data, ensure_ascii=False, separators=(",", ":"))
            )},
        ],
    }
    if request_timeout is not None:
        request["timeout"] = request_timeout
    response = client.responses.create(**request)
    if getattr(response, "status", None) != "completed" or not response.output_text:
        raise RuntimeError("La auditoría del modelo no terminó correctamente.")
    try:
        model_audit = ModelAudit.model_validate_json(response.output_text)
    except ValidationError as exc:
        raise RuntimeError("La respuesta clínica no cumplió el contrato JSON.") from exc
    findings: dict[str, Any] = {}
    for finding in model_audit.hallazgos:
        if finding.idItem in findings:
            raise RuntimeError("La respuesta clínica contiene medicamentos duplicados.")
        findings[finding.idItem] = finding
    if set(findings) != {item["idItem"] for item in clinical_data["medicamentos"]}:
        raise RuntimeError("La respuesta clínica no corresponde a todos los medicamentos.")
    searched, sources = _searched_sources(response)
    return response, findings, searched, sources


def _verified_sources(
    finding: Any, searched: bool, sources: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    if not searched:
        return []
    verified = []
    for url in finding.fuentes:
        canonical = _canonical_url(url)
        if canonical in sources and sources[canonical] not in verified:
            verified.append(sources[canonical])
    return verified


def process_request_payload(raw_payload: dict[str, Any], client: Any = None) -> dict[str, Any]:
    started = time.monotonic()
    clinical_data = project_clinical_data(raw_payload)
    selected_client = client if client is not None else build_client()
    response, raw_findings, searched, sources = _run_audit(
        selected_client, clinical_data, USER_PROMPT
    )
    verified_by_id = {
        item_id: _verified_sources(finding, searched, sources)
        for item_id, finding in raw_findings.items()
    }
    needs_review = [item for item in clinical_data["medicamentos"]
                    if not verified_by_id[item["idItem"]]
                    or raw_findings[item["idItem"]].juicio == "insuficiente"]
    total_tokens = getattr(getattr(response, "usage", None), "total_tokens", None)
    if needs_review:
        focused_data = {"edad": clinical_data["edad"],
                        "diagnosticos": clinical_data["diagnosticos"],
                        "medicamentos": needs_review}
        try:
            retry_response, retry_findings, retry_searched, retry_sources = _run_audit(
                selected_client, focused_data, RETRY_PROMPT,
                search_context_size="high", request_timeout=75.0,
            )
        except Exception:
            # La segunda búsqueda es opcional; conservar el primer dictamen si falla.
            pass
        else:
            retry_tokens = getattr(getattr(retry_response, "usage", None), "total_tokens", None)
            if isinstance(retry_tokens, int):
                total_tokens = (total_tokens or 0) + retry_tokens
            for item_id, finding in retry_findings.items():
                verified = _verified_sources(finding, retry_searched, retry_sources)
                if verified and (not verified_by_id[item_id] or finding.juicio != "insuficiente"):
                    raw_findings[item_id] = finding
                    verified_by_id[item_id] = verified

    findings = []
    for item in clinical_data["medicamentos"]:
        raw = raw_findings[item["idItem"]]
        verified = verified_by_id[item["idItem"]]
        if not verified:
            findings.append(_empty_finding(
                item, "No se pudo verificar una fuente web confiable para este hallazgo."
            ))
            continue
        findings.append({
            "idItem": item["idItem"], "tipo": item["tipo"],
            "descripcion": _item_description(item), "juicio": raw.juicio,
            "prioridad": raw.prioridad if raw.juicio == "alerta" else "ninguna",
            "fundamentoClinico": raw.fundamentoClinico,
            "informacionFaltante": raw.informacionFaltante,
            "fuentes": verified,
            "requiereRevisionClinicaAdicional": raw.juicio != "compatible",
        })
    counts = {name: sum(item["juicio"] == name for item in findings)
              for name in ("compatible", "alerta", "insuficiente")}
    status = ("requiere_revision_clinica" if counts["alerta"] else
              "evidencia_insuficiente" if counts["insuficiente"] else
              "sin_objeciones_clinicas_detectadas")
    authorization_assessment = ("objeciones_clinicas" if counts["alerta"] else
                                "indeterminada" if counts["insuficiente"] else
                                "congruente_con_datos")
    return {
        "modelo": MODEL_NAME, "versionContrato": "2.2",
        "fechaAuditoriaUTC": datetime.now(timezone.utc).isoformat(),
        "tokensUsados": total_tokens,
        "tiempoRespuestaSegundos": round(time.monotonic() - started, 3),
        "data": {
            "estadoAuditoria": status,
            "evaluacionMedicaAutorizacion": authorization_assessment,
            "datosEvaluados": clinical_data,
            "resumen": {"totalMedicamentos": len(findings), **counts,
                        "requierenRevisionClinicaAdicional": counts["alerta"] + counts["insuficiente"]},
            "hallazgos": findings,
            "nota": "Compatible indica pertinencia clínica razonable con los datos recibidos. La revisión clínica adicional se señala solo para alertas o información decisiva insuficiente. Si la solicitud es histórica, la edad calculada hoy desde el nacimiento puede diferir de la edad al autorizar.",
        },
    }
