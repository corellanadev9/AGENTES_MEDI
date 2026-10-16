import json
from typing import Any

from .pipeline import process_request_payload


def handle_request_payload(raw_payload: dict[str, Any]) -> dict[str, Any]:
    return process_request_payload(raw_payload)


def handle_request_json(raw_json: str) -> str:
    return json.dumps(handle_request_payload(json.loads(raw_json)), ensure_ascii=False)
