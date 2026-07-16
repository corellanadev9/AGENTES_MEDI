import json
import os
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, initialize_app
from firebase_functions import https_fn

from agentBaseMediprocesos.service import handle_request_payload as agent_base_handler
from proveedores.providerSyncHomologador.service import (
    handle_request_payload as provider_sync_homologador_handler,
)


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SERVICE_ACCOUNT = BASE_DIR / "script" / "keys" / "firebase-sa.json"
FIREBASE_SERVICE_ACCOUNT_PATH = Path(
    os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", str(DEFAULT_SERVICE_ACCOUNT))
)


def initialize_firebase() -> None:
    if firebase_admin._apps:
        return

    if FIREBASE_SERVICE_ACCOUNT_PATH.exists():
        cred = credentials.Certificate(str(FIREBASE_SERVICE_ACCOUNT_PATH))
        initialize_app(cred)
    else:
        # Permite usar credenciales por defecto del entorno cuando la llave local no exista.
        initialize_app()


initialize_firebase()


def json_response(payload: dict, status: int = 200) -> https_fn.Response:
    return https_fn.Response(
        json.dumps(payload, ensure_ascii=False),
        status=status,
        mimetype="application/json",
    )


@https_fn.on_request()
def health_check(req: https_fn.Request) -> https_fn.Response:
    return json_response(
        {
            "ok": True,
            "service": "agentes-medi",
            "message": "Firebase Functions funcionando correctamente.",
        }
    )


@https_fn.on_request()
def agent_base_api(req: https_fn.Request) -> https_fn.Response:
    if req.method != "POST":
        return json_response(
            {
                "ok": False,
                "error": "Method not allowed. Usa POST.",
            },
            status=405,
        )

    try:
        payload = req.get_json(silent=True) or {}
        result = agent_base_handler(payload)
        return json_response(
            {
                "ok": True,
                "agent": "agentBaseMediprocesos",
                "result": result,
            }
        )
    except Exception as exc:
        return json_response(
            {
                "ok": False,
                "error": str(exc),
            },
            status=500,
        )


@https_fn.on_request()
def example_agent_router(req: https_fn.Request) -> https_fn.Response:
    if req.method != "POST":
        return json_response(
            {
                "ok": False,
                "error": "Method not allowed. Usa POST.",
            },
            status=405,
        )

    payload = req.get_json(silent=True) or {}
    agent_name = payload.get("agent")

    handlers = {
        "agentBaseMediprocesos": agent_base_handler,
        "providerSyncHomologador": provider_sync_homologador_handler,
    }

    if agent_name not in handlers:
        return json_response(
            {
                "ok": False,
                "error": "Agente no soportado.",
                "availableAgents": sorted(handlers.keys()),
            },
            status=400,
        )

    try:
        result = handlers[agent_name](payload)
        return json_response(
            {
                "ok": True,
                "agent": agent_name,
                "result": result,
            }
        )
    except Exception as exc:
        return json_response(
            {
                "ok": False,
                "agent": agent_name,
                "error": str(exc),
            },
            status=500,
        )


@https_fn.on_request()
def provider_sync_homologador_api(req: https_fn.Request) -> https_fn.Response:
    if req.method != "POST":
        return json_response(
            {
                "ok": False,
                "error": "Method not allowed. Usa POST.",
            },
            status=405,
        )

    try:
        payload = req.get_json(silent=True) or {}
        result = provider_sync_homologador_handler(payload)
        return json_response(
            {
                "ok": True,
                "agent": "providerSyncHomologador",
                "result": result,
            }
        )
    except Exception as exc:
        return json_response(
            {
                "ok": False,
                "error": str(exc),
            },
            status=500,
        )
