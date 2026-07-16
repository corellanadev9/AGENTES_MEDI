from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ServiceRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    rowNumber: Optional[int] = Field(default=None, description="Numero de fila de referencia.")
    tipoServicio: Optional[int | str] = None
    codigoServicio: str
    nombreServicio: str
    moneda: Optional[int | str] = None
    precio: Optional[float | int | str] = None
    tipoProveedor: Optional[int | str] = None
    codigoProveedor: Optional[int | str] = None
    nombreProveedor: Optional[str] = None


class AgentInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    rows: list[ServiceRow] = Field(default_factory=list)
    filePath: Optional[str] = Field(
        default=None,
        description="Ruta local a un archivo .xlsx, .xlsm, .csv o .tsv.",
    )
    fileName: Optional[str] = None
    excelBase64: Optional[str] = Field(
        default=None,
        description="Contenido base64 del archivo Excel o CSV.",
    )
    csvText: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    batchSize: int = Field(default=20, ge=1, le=50)
    enableWebSearch: bool = True

    @model_validator(mode="after")
    def validate_input_source(self) -> "AgentInput":
        if self.rows or self.filePath or self.excelBase64 or self.csvText:
            return self
        raise ValueError("Debes enviar rows, filePath, excelBase64 o csvText.")


class CandidateCode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str
    nombre: str
    motivo: str


class WebSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: str
    url: str


class HomologatedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rowNumber: int
    codigoServicio: str
    nombreServicioOriginal: str
    nombreServicioEstandar: Optional[str] = None
    categoriaEstandar: Optional[str] = None
    codigoMedicalFiis: Optional[str] = None
    confianza: Literal["alta", "media", "baja"]
    requiereRevisionHumana: bool
    codigosCandidatos: list[CandidateCode] = Field(default_factory=list)
    fuentesWeb: list[WebSource] = Field(default_factory=list)
    observaciones: Optional[str] = None


class ProcessingSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    totalItems: int
    itemsConCodigoPrincipal: int
    itemsParaRevision: int


class AgentData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proveedor: Optional[str] = None
    tipoProveedor: Optional[str] = None
    archivoProcesado: Optional[str] = None
    totalFilasEntrada: int
    items: list[HomologatedItem]
    resumen: ProcessingSummary


class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modelo: str
    tokensUsados: Optional[int] = None
    tiempoRespuestaSegundos: str
    data: AgentData

