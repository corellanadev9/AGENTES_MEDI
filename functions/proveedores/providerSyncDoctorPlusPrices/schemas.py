from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def clean_code(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    return text or None


class DoctorPlusPriceRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rowNumber: int = Field(ge=1)
    codigoServicio: Optional[str] = None
    nombreServicio: str = Field(min_length=1)

    @field_validator("codigoServicio", mode="before")
    @classmethod
    def normalize_service_code(cls, value: Any) -> Optional[str]:
        return clean_code(value)

    @field_validator("nombreServicio", mode="before")
    @classmethod
    def normalize_service_name(cls, value: Any) -> str:
        return clean_text(value)


class DoctorPlusAgentInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rows: list[DoctorPlusPriceRow] = Field(min_length=1, max_length=200)
    batchSize: int = Field(default=25, ge=1, le=50)
    maxCandidates: int = Field(default=5, ge=1, le=8)


class MedicalFeesCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str
    nombre: str
    categoria: Optional[str] = None
    scorePreliminar: int = Field(ge=0, le=100)


class DoctorPlusHomologatedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rowNumber: int
    codigoServicioOmega: Optional[str] = None
    nombreServicioOriginal: str
    estadoAsociacion: Literal["asociado", "sin_asociacion"]
    codigoProviderSync: Optional[str] = None
    nombreMedicalFees: Optional[str] = None
    categoriaMedicalFees: Optional[str] = None
    confianzaPorcentaje: int = Field(ge=0, le=100)
    requiereRevisionHumana: bool
    motivo: str
    candidatos: list[MedicalFeesCandidate] = Field(default_factory=list)


class DoctorPlusSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    totalItems: int
    itemsAsociados: int
    itemsSinAsociacion: int
    itemsParaRevision: int


class DoctorPlusAgentData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    totalFilasEntrada: int
    items: list[DoctorPlusHomologatedItem]
    resumen: DoctorPlusSummary


class DoctorPlusAgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modelo: str
    versionContrato: str = "1.0"
    tokensUsados: Optional[int] = None
    tiempoRespuestaSegundos: str
    data: DoctorPlusAgentData
