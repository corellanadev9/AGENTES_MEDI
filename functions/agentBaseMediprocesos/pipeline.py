import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

from openai import OpenAI

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

try:
    from .prompts import SYSTEM_PROMPT, USER_PROMPT
    from .schemas import AgentData, AgentInput, AgentResponse
except ImportError:
    from prompts import SYSTEM_PROMPT, USER_PROMPT
    from schemas import AgentData, AgentInput, AgentResponse


MODEL_NAME = "gpt-5.4-mini"


def build_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("No se encontró OPENAI_API_KEY en variables de entorno.")
    return OpenAI(api_key=api_key)


def run_agent(payload: AgentInput, client: Optional[OpenAI] = None) -> tuple[str, Optional[int]]:
    if client is None:
        client = build_client()

    rendered_prompt = USER_PROMPT.format(
        json.dumps(payload.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=2)
    )
    response = client.responses.create(
        model=MODEL_NAME,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": rendered_prompt},
        ],
    )
    return (response.output_text or "").strip(), getattr(getattr(response, "usage", None), "total_tokens", None)


def process_request_payload(
    raw_payload: dict,
    client: Optional[OpenAI] = None,
) -> AgentResponse:
    started = time.monotonic()
    payload = AgentInput.model_validate(raw_payload)
    output_text, total_tokens = run_agent(payload, client=client)
    elapsed = f"{(time.monotonic() - started):.6f}"

    data = AgentData(
        resultado=output_text or "Sin respuesta del modelo.",
        observaciones="Plantilla base: adaptar schema y postproceso según el agente real.",
    )
    return AgentResponse(
        modelo=MODEL_NAME,
        tokensUsados=total_tokens,
        tiempoRespuestaSegundos=elapsed,
        data=data,
    )


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Uso: python3 pipeline.py '{\"message\":\"Hola agente\",\"metadata\":{\"source\":\"local\"}}'"
        )

    payload = json.loads(sys.argv[1])
    result = process_request_payload(payload)
    print(json.dumps(result.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
