import json
from typing import Any

try:
    from .pipeline import process_request_payload
except ImportError:
    from pipeline import process_request_payload


def handle_request_payload(raw_payload: dict[str, Any]) -> dict[str, Any]:
    response = process_request_payload(raw_payload)
    return response.model_dump(mode="json", exclude_none=True)


def handle_request_json(raw_json: str) -> str:
    payload = json.loads(raw_json)
    return json.dumps(handle_request_payload(payload), ensure_ascii=False, separators=(",", ":"))
