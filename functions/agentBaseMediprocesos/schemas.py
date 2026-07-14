from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    message: str = Field(description="Mensaje principal para el agente.")
    metadata: Optional[dict[str, Any]] = None


class AgentData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resultado: str
    observaciones: Optional[str] = None


class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modelo: str
    tokensUsados: Optional[int] = None
    tiempoRespuestaSegundos: str
    data: AgentData
