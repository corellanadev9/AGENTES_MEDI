from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idItem: str
    juicio: Literal["compatible", "alerta", "insuficiente"]
    prioridad: Literal["ninguna", "baja", "media", "alta"]
    fundamentoClinico: str
    informacionFaltante: list[str]
    fuentes: list[str]


class ModelAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hallazgos: list[ModelFinding]


MODEL_AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "hallazgos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "idItem": {"type": "string"},
                    "juicio": {"type": "string", "enum": ["compatible", "alerta", "insuficiente"]},
                    "prioridad": {"type": "string", "enum": ["ninguna", "baja", "media", "alta"]},
                    "fundamentoClinico": {"type": "string"},
                    "informacionFaltante": {"type": "array", "items": {"type": "string"}},
                    "fuentes": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "idItem", "juicio", "prioridad", "fundamentoClinico",
                    "informacionFaltante", "fuentes",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["hallazgos"],
    "additionalProperties": False,
}
