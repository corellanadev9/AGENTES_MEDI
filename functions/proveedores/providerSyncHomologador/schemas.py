from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def first_present(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def clean_code(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


class ServiceRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    rowNumber: Optional[int] = Field(default=None, description="Numero de fila de referencia.")
    tipoServicio: Optional[int | str] = None
    codigoServicio: str = Field(min_length=1)
    nombreServicio: str = Field(min_length=1)
    moneda: Optional[int | str] = None
    precio: Optional[float | int | str] = None
    fechaInicio: Optional[str | date | datetime] = None
    observaciones: Optional[str] = None
    tipoProveedor: Optional[int | str] = None
    codigoProveedor: Optional[int | str] = None
    nombreProveedor: Optional[str] = None

    @field_validator("codigoServicio", mode="before")
    @classmethod
    def normalize_service_code(cls, value: Any) -> str:
        return clean_code(value)

    @field_validator("nombreServicio", mode="before")
    @classmethod
    def normalize_service_name(cls, value: Any) -> str:
        return str(value or "").strip()


class CptCatalogItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    idCptProduct: Optional[int | str] = None
    codigoCpt: str = Field(min_length=1)
    nombreCpt: str = Field(min_length=1)
    tipoProcedimientoId: Optional[int | str] = None
    tipoProcedimientoNombre: Optional[str] = None
    tipoCptId: Optional[int | str] = None
    tipoCptNombre: Optional[str] = None
    estado: Optional[int | str] = None

    @model_validator(mode="before")
    @classmethod
    def accept_provider_sync_names(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        data.setdefault(
            "idCptProduct",
            first_present(data, "idCptProduct", "id", "idProductoCpt"),
        )
        data.setdefault(
            "codigoCpt",
            first_present(data, "codigoCpt", "code", "codigo", "cpt"),
        )
        data.setdefault(
            "nombreCpt",
            first_present(data, "nombreCpt", "description", "descripcion", "nombre"),
        )
        data.setdefault(
            "tipoProcedimientoId",
            first_present(data, "tipoProcedimientoId", "idProcedureType"),
        )
        data.setdefault(
            "tipoProcedimientoNombre",
            first_present(data, "tipoProcedimientoNombre", "procedureType", "tipo"),
        )
        data.setdefault(
            "tipoCptId",
            first_present(data, "tipoCptId", "idCpt", "cptTypeId"),
        )
        data.setdefault(
            "tipoCptNombre",
            first_present(
                data,
                "tipoCptNombre",
                "cptTypeName",
                "clasificacionCpt",
            ),
        )
        data.setdefault(
            "estado",
            first_present(data, "estado", "stateProduct", "state"),
        )
        return data

    @field_validator("codigoCpt", mode="before")
    @classmethod
    def normalize_cpt_code(cls, value: Any) -> str:
        return clean_code(value)

    @field_validator("nombreCpt", mode="before")
    @classmethod
    def normalize_cpt_name(cls, value: Any) -> str:
        return str(value or "").strip()


class ServiceTypeCatalogItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    idTipoServicio: int | str
    nombreTipoServicio: str = Field(min_length=1)
    abreviatura: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def accept_provider_sync_names(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        data.setdefault(
            "idTipoServicio",
            first_present(
                data,
                "idTipoServicio",
                "idServiceType",
                "ID_SERVICE_TYPE",
                "id",
                "codigo",
            ),
        )
        data.setdefault(
            "nombreTipoServicio",
            first_present(
                data,
                "nombreTipoServicio",
                "description",
                "DESCRIPTION",
                "descripcion",
                "nombre",
            ),
        )
        data.setdefault(
            "abreviatura",
            first_present(data, "abreviatura", "abbreviation"),
        )
        return data


class AgentInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    rows: list[dict[str, Any]] = Field(default_factory=list)
    filePath: Optional[str] = Field(
        default=None,
        description="Ruta local a un archivo .xlsx, .xlsm, .csv, .tsv o .txt.",
    )
    fileName: Optional[str] = None
    excelBase64: Optional[str] = Field(
        default=None,
        description="Contenido base64 del archivo soportado.",
    )
    csvText: Optional[str] = None
    catalogoCpt: list[CptCatalogItem] = Field(default_factory=list)
    catalogoTiposServicio: list[ServiceTypeCatalogItem] = Field(default_factory=list)
    metadata: Optional[dict[str, Any]] = None
    batchSize: int = Field(default=15, ge=1, le=30)
    maxCandidates: int = Field(default=5, ge=1, le=10)
    enableWebSearch: bool = False

    @model_validator(mode="after")
    def validate_input_source(self) -> "AgentInput":
        if self.rows or self.filePath or self.excelBase64 or self.csvText:
            return self
        raise ValueError("Debes enviar rows, filePath, excelBase64 o csvText.")


class CandidateCode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fuente: Literal["catalogo_cpt", "medical_fees"]
    idCptProduct: Optional[int | str] = None
    codigo: str
    nombre: str
    nombreOriginal: Optional[str] = None
    tipoProcedimiento: Optional[str] = None
    tipoCptId: Optional[int | str] = None
    tipoCptNombre: Optional[str] = None
    paginaMedicalFees: Optional[int] = None
    categoria: Optional[str] = None
    scorePreliminar: Optional[int] = Field(default=None, ge=0, le=100)
    motivo: str


class WebSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: str
    url: str


class MedicalFeesTranslation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str
    nombreEspanol: str


class HomologatedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rowNumber: int
    codigoServicio: str
    nombreServicioOriginal: str
    precio: Optional[float | int | str] = None
    fechaInicio: Optional[str] = None
    observacionesArchivo: Optional[str] = None
    estadoAsociacion: Literal["asociado", "cpt_nuevo_sugerido", "sin_asociacion"]
    fuenteAsociacion: Literal["catalogo_cpt", "medical_fees", "sin_coincidencia"]
    idCptProduct: Optional[int | str] = None
    codigoCpt: Optional[str] = None
    nombreCpt: Optional[str] = None
    nombreCptOriginal: Optional[str] = None
    codigoMedicalFees: Optional[str] = None
    paginaMedicalFees: Optional[int] = None
    categoria: Optional[str] = None
    tipoCptId: Optional[int | str] = None
    tipoCptNombre: Optional[str] = None
    tipoServicioId: Optional[int | str] = None
    tipoServicioNombre: Optional[str] = None
    confianzaPorcentaje: int = Field(ge=0, le=100)
    confianza: Literal["alta", "media", "baja"]
    requiereRevisionHumana: bool
    motivo: str
    codigosCandidatos: list[CandidateCode] = Field(default_factory=list)
    traduccionesMedicalFees: list[MedicalFeesTranslation] = Field(
        default_factory=list,
        exclude=True,
    )
    fuentesWeb: list[WebSource] = Field(default_factory=list)
    observaciones: Optional[str] = None


class ProcessingSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    totalItems: int
    itemsAsociadosCatalogo: int
    itemsCptNuevoSugerido: int
    itemsSinAsociacion: int
    itemsParaRevision: int


class AgentData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proveedor: Optional[str] = None
    codigoProveedor: Optional[str] = None
    tipoProveedor: Optional[str] = None
    archivoProcesado: Optional[str] = None
    totalFilasEntrada: int
    items: list[HomologatedItem]
    resumen: ProcessingSummary


class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modelo: str
    versionContrato: str = "2.2"
    tokensUsados: Optional[int] = None
    tiempoRespuestaSegundos: str
    data: AgentData
