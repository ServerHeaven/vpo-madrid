"""Typed mirror of data/schema/promocion.schema.json.

The JSON Schema is the source of truth; tests/test_models.py keeps both in step.
Every field is required: unknown values are an explicit ``None``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Slug = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)]
SimpleId = Annotated[str, Field(pattern=r"^[a-z0-9-]+$")]
MunicipioIne = Annotated[str, Field(pattern=r"^28[0-9]{3}$")]
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Pointer = Annotated[str, Field(pattern=r"^/")]
Eur = Annotated[float, Field(ge=0, le=10000)]
VecesIprem = Annotated[float, Field(ge=0, le=15)]

Regimen = Literal["VPPB", "VPPL", "VPPA", "VPO", "ASEQUIBLE_NO_CALIFICADA", "DESCONOCIDO"]
Programa = Literal[
    "PLAN_VIVE", "EMVS_MADRID", "EMV_MUNICIPAL", "AVS_CAM", "COOPERATIVA", "PROMOTOR_PRIVADO", "OTRO"
]
Estado = Literal[
    "proxima",
    "inscripcion_abierta",
    "inscripcion_cerrada",
    "sorteo_adjudicacion",
    "lista_espera_abierta",
    "finalizada",
    "desconocido",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Operador(_Strict):
    id: SimpleId
    nombre: str
    tipo: Literal["publico_autonomico", "publico_municipal", "privado_concesionario", "cooperativa", "otro"]


class Ubicacion(_Strict):
    municipio_ine: MunicipioIne
    municipio: str
    distrito: str | None
    direccion: str | None
    lat: Annotated[float, Field(ge=39.8, le=41.2)] | None
    lon: Annotated[float, Field(ge=-4.6, le=-3.0)] | None


class Anejo(_Strict):
    disponibilidad: Literal["incluido", "opcional", "no", "desconocido"]
    precio_mensual_eur: Eur | None


class Tipologia(_Strict):
    dormitorios: Annotated[int, Field(ge=0, le=6)] | None
    superficie_util_m2: Annotated[float, Field(ge=15, le=200)] | None
    renta_mensual_eur: Eur | None
    renta_mensual_max_eur: Eur | None
    num_viviendas: Annotated[int, Field(ge=1)] | None
    garaje: Anejo
    trastero: Anejo
    adaptada_pmr: bool | None


class IngresosPorMiembros(_Strict):
    miembros_desde: Annotated[int, Field(ge=1)]
    miembros_hasta: Annotated[int, Field(ge=1)] | None
    min_iprem: VecesIprem | None
    max_iprem: VecesIprem | None


class Empadronamiento(_Strict):
    ambito: Literal["municipio", "comunidad"]
    municipio_ine: MunicipioIne | None
    anios_min: Annotated[float, Field(ge=0, le=20)] | None
    ininterrumpido: bool | None
    alternativa_trabajo: bool | None


class Edad(_Strict):
    min: Annotated[int, Field(ge=16, le=99)] | None
    max: Annotated[int, Field(ge=16, le=120)] | None
    tipo: Literal["requisito", "cupo"]


NoExigido = Literal[
    "ingresos_min_iprem",
    "ingresos_max_iprem",
    "tasa_esfuerzo_max",
    "empadronamiento",
    "edad",
    "no_titular_vivienda",
]


class Requisitos(_Strict):
    ingresos_min_iprem: VecesIprem | None
    ingresos_max_iprem: VecesIprem | None
    ingresos_por_miembros: list[IngresosPorMiembros] | None
    iprem_pagas: Literal[12, 14] | None
    iprem_ejercicio: Annotated[int, Field(ge=2015, le=2100)] | None
    tasa_esfuerzo_max: Annotated[float, Field(gt=0, le=1)] | None
    empadronamiento: Empadronamiento | None
    edad: Edad | None
    no_titular_vivienda: bool | None
    no_exigidos: list[NoExigido]
    otros: list[Annotated[str, Field(max_length=300)]]


class Fechas(_Strict):
    inscripcion_inicio: date | None
    inscripcion_fin: date | None
    sorteo: date | None
    entrega_prevista: Annotated[str, Field(pattern=r"^[0-9]{4}(-(T[1-4]|0[1-9]|1[0-2]))?$")] | None


class DocumentoBases(_Strict):
    url: str
    titulo: str
    sha256: Sha256
    detectado_en: date
    es_principal: bool


class Enlaces(_Strict):
    oficial: str
    solicitud: str | None
    bases: list[DocumentoBases]


class Procedencia(_Strict):
    metodo: Literal["html", "pdf_texto", "pdf_tabla", "override", "default_programa", "llm"]
    confianza: Annotated[float, Field(ge=0, le=1)]
    documento: str | None
    pagina: Annotated[int, Field(ge=1)] | None
    evidencia: Annotated[str, Field(max_length=400)] | None
    regla: str | None


class Meta(_Strict):
    primera_deteccion: date
    ultima_modificacion: date
    activa_en_fuente: bool
    campos_pendientes: list[Pointer]
    campos_override: list[Pointer]
    procedencia: dict[str, Procedencia]
    extractor_version: Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")]


class Promocion(_Strict):
    id: Slug
    nombre: Annotated[str, Field(min_length=2, max_length=200)]
    operador: Operador
    fuente_id: SimpleId
    regimen: Regimen
    programa: Programa | None
    modalidad: Literal["alquiler", "alquiler_opcion_compra"] | None
    estado: Estado
    ubicacion: Ubicacion
    viviendas_total: Annotated[int, Field(ge=1, le=5000)] | None
    tipologias: list[Tipologia]
    requisitos: Requisitos
    fechas: Fechas
    enlaces: Enlaces
    meta: Meta


class Promociones(_Strict):
    schema_version: Literal[1]
    generado_en: datetime
    promociones: list[Promocion]
