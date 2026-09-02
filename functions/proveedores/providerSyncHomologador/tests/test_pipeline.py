import json
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from proveedores.providerSyncHomologador.matching import (
    SearchRecord,
    TextCandidateIndex,
    normalize_text,
)
from proveedores.providerSyncHomologador.medical_fees import parse_medical_fees_page
from proveedores.providerSyncHomologador.medical_fees_excel import (
    load_medical_fees_excel_records,
)
from proveedores.providerSyncHomologador.prompts import SYSTEM_PROMPT
from proveedores.providerSyncHomologador.pipeline import (
    candidate_models,
    collect_rows,
    load_rows_from_delimited_text,
    process_request_payload,
)
from proveedores.providerSyncHomologador.schemas import AgentInput


class FakeResponses:
    def __init__(self):
        self.last_request_args = None

    def create(self, **request_args):
        self.last_request_args = request_args
        output = {
            "items": [
                {
                    "rowNumber": 2,
                    "codigoServicio": "13.04.13",
                    "nombreServicioOriginal": "MAXILAR INFERIOR O SUPERIOR",
                    "precio": "Q200,00",
                    "fechaInicio": "03/10/2025",
                    "observacionesArchivo": None,
                    "estadoAsociacion": "asociado",
                    "fuenteAsociacion": "catalogo_cpt",
                    "idCptProduct": 99,
                    "codigoCpt": "70100",
                    "nombreCpt": "RAYOS X DE MANDIBULA, MENOS DE 4 VISTAS",
                    "codigoMedicalFees": "70100",
                    "paginaMedicalFees": None,
                    "tipoServicioId": 7,
                    "tipoServicioNombre": "Rayos X",
                    "confianzaPorcentaje": 93,
                    "confianza": "alta",
                    "requiereRevisionHumana": False,
                    "motivo": "Coinciden anatomia y alcance radiologico.",
                    "codigosCandidatos": ["70100", "70110"],
                    "fuentesWeb": [],
                    "observaciones": None,
                }
            ]
        }
        return SimpleNamespace(
            output_text=json.dumps(output),
            usage=SimpleNamespace(total_tokens=125),
        )


class FakeClient:
    def __init__(self):
        self.responses = FakeResponses()


class InvalidCodeResponses:
    def create(self, **request_args):
        output = {
            "items": [
                {
                    "rowNumber": 2,
                    "codigoServicio": "13.04.13",
                    "nombreServicioOriginal": "MAXILAR INFERIOR O SUPERIOR",
                    "estadoAsociacion": "asociado",
                    "fuenteAsociacion": "catalogo_cpt",
                    "codigoCpt": "99999",
                    "nombreCpt": "CODIGO INVENTADO",
                    "tipoServicioId": 999,
                    "tipoServicioNombre": "Tipo inventado",
                    "confianzaPorcentaje": 99,
                    "confianza": "alta",
                    "requiereRevisionHumana": False,
                    "motivo": "Respuesta no verificable.",
                }
            ]
        }
        return SimpleNamespace(
            output_text=json.dumps(output),
            usage=SimpleNamespace(total_tokens=25),
        )


class InvalidCodeClient:
    def __init__(self):
        self.responses = InvalidCodeResponses()


class InvalidServiceTypeResponses(FakeResponses):
    def create(self, **request_args):
        response = super().create(**request_args)
        output = json.loads(response.output_text)
        output["items"][0]["tipoServicioId"] = 999
        output["items"][0]["tipoServicioNombre"] = "Tipo inventado"
        return SimpleNamespace(
            output_text=json.dumps(output),
            usage=response.usage,
        )


class InvalidServiceTypeClient:
    def __init__(self):
        self.responses = InvalidServiceTypeResponses()


class InvalidConfidenceLabelResponses(FakeResponses):
    def create(self, **request_args):
        response = super().create(**request_args)
        output = json.loads(response.output_text)
        output["items"][0]["confianzaPorcentaje"] = 85
        output["items"][0]["confianza"] = "sin_evidencia"
        output["items"][0]["requiereRevisionHumana"] = True
        return SimpleNamespace(
            output_text=json.dumps(output),
            usage=response.usage,
        )


class InvalidConfidenceLabelClient:
    def __init__(self):
        self.responses = InvalidConfidenceLabelResponses()


class MedicalTranslationResponses:
    def __init__(self, confidence=80):
        self.confidence = confidence

    def create(self, **request_args):
        output = {
            "items": [
                {
                    "rowNumber": 9,
                    "codigoServicio": "13,04",
                    "nombreServicioOriginal": "SENOS PARANASALES",
                    "estadoAsociacion": "cpt_nuevo_sugerido",
                    "fuenteAsociacion": "medical_fees",
                    "codigoCpt": "70210",
                    "nombreCpt": (
                        "Examen radiologico de senos paranasales, "
                        "menos de 3 vistas"
                    ),
                    "nombreCptOriginal": (
                        "Radiologic examination, sinuses, paranasal, "
                        "less than 3 views"
                    ),
                    "codigoMedicalFees": "70210",
                    "paginaMedicalFees": 424,
                    "tipoServicioId": 5,
                    "tipoServicioNombre": "Rayos X",
                    "confianzaPorcentaje": self.confidence,
                    "confianza": "alta" if self.confidence >= 80 else "media",
                    "requiereRevisionHumana": self.confidence < 80,
                    "motivo": "Coinciden anatomia y cantidad de vistas.",
                    "traduccionesMedicalFees": [
                        {
                            "codigo": "70210",
                            "nombreEspanol": (
                                "Examen radiologico de los senos paranasales, "
                                "menos de 3 vistas"
                            ),
                        }
                    ],
                }
            ]
        }
        return SimpleNamespace(
            output_text=json.dumps(output),
            usage=SimpleNamespace(total_tokens=40),
        )


class MedicalTranslationClient:
    def __init__(self, confidence=80):
        self.responses = MedicalTranslationResponses(confidence)


class ExcelFirstResponses:
    def __init__(self, initial_confidence=91):
        self.initial_confidence = initial_confidence
        self.calls = 0

    def create(self, **request_args):
        self.calls += 1
        if self.calls == 1:
            selected = {
                "codigoCpt": "701002",
                "nombreCpt": (
                    "RAYOS X DE MANDIBULA / MAXILAR SUPERIOR INFERIOR "
                    "(3 PROYECCIONES)"
                ),
                "nombreCptOriginal": (
                    "RAYOS X DE MANDIBULA / MAXILAR SUPERIOR INFERIOR "
                    "(3 PROYECCIONES)"
                ),
                "paginaMedicalFees": None,
                "categoria": "RX",
                "confianzaPorcentaje": self.initial_confidence,
            }
        else:
            selected = {
                "codigoCpt": "70110",
                "nombreCpt": (
                    "Examen radiologico completo de mandibula, minimo 4 vistas"
                ),
                "nombreCptOriginal": (
                    "Radiologic examination, mandible; complete, "
                    "minimum of 4 views"
                ),
                "paginaMedicalFees": 423,
                "categoria": None,
                "confianzaPorcentaje": 94,
            }
        confidence = selected["confianzaPorcentaje"]
        output = {
            "items": [
                {
                    "rowNumber": 2,
                    "codigoServicio": "13.04.61",
                    "nombreServicioOriginal": "MANDIBULA 3 VISTAS",
                    "estadoAsociacion": "cpt_nuevo_sugerido",
                    "fuenteAsociacion": "medical_fees",
                    "codigoCpt": selected["codigoCpt"],
                    "nombreCpt": selected["nombreCpt"],
                    "nombreCptOriginal": selected["nombreCptOriginal"],
                    "codigoMedicalFees": selected["codigoCpt"],
                    "paginaMedicalFees": selected["paginaMedicalFees"],
                    "categoria": selected["categoria"],
                    "tipoServicioId": 5,
                    "tipoServicioNombre": "Rayos X",
                    "confianzaPorcentaje": confidence,
                    "confianza": "alta" if confidence >= 80 else "media",
                    "requiereRevisionHumana": confidence < 80,
                    "motivo": "Coincidencia clinica verificada.",
                }
            ]
        }
        return SimpleNamespace(
            output_text=json.dumps(output),
            usage=SimpleNamespace(total_tokens=30),
        )


class ExcelFirstClient:
    def __init__(self, initial_confidence=91):
        self.responses = ExcelFirstResponses(initial_confidence)


class ConcurrentResponses:
    def __init__(self):
        self.active_calls = 0
        self.max_active_calls = 0
        self.lock = threading.Lock()

    def create(self, **request_args):
        with self.lock:
            self.active_calls += 1
            self.max_active_calls = max(
                self.max_active_calls,
                self.active_calls,
            )

        try:
            time.sleep(0.04)
            user_prompt = request_args["input"][1]["content"]
            rows_json = user_prompt.split(
                "Filas y candidatos verificados:\n",
                1,
            )[1].strip()
            enriched_rows = json.loads(rows_json)
            items = []
            for row in enriched_rows:
                candidate = row["candidatosCatalogoCpt"][0]
                items.append(
                    {
                        "rowNumber": row["rowNumber"],
                        "codigoServicio": row["codigoServicio"],
                        "nombreServicioOriginal": row["nombreServicio"],
                        "estadoAsociacion": "asociado",
                        "fuenteAsociacion": "catalogo_cpt",
                        "idCptProduct": candidate["idCptProduct"],
                        "codigoCpt": candidate["codigo"],
                        "nombreCpt": candidate["nombre"],
                        "tipoServicioId": 5,
                        "tipoServicioNombre": "Rayos X",
                        "confianzaPorcentaje": 90,
                        "confianza": "alta",
                        "requiereRevisionHumana": False,
                        "motivo": "Coincidencia exacta verificada.",
                    }
                )
            return SimpleNamespace(
                output_text=json.dumps({"items": items}),
                usage=SimpleNamespace(total_tokens=10),
            )
        finally:
            with self.lock:
                self.active_calls -= 1


class ConcurrentClient:
    def __init__(self):
        self.responses = ConcurrentResponses()


class ProviderSyncHomologadorTests(unittest.TestCase):
    def test_prompt_includes_safe_human_validated_equivalences(self):
        self.assertIn("proyeccion y vista describen el mismo concepto", SYSTEM_PROMPT)
        self.assertIn('"minimo 4" no equivale', SYSTEM_PROMPT)
        self.assertIn("Trifasica y 3 fases son equivalentes", SYSTEM_PROMPT)
        self.assertIn("derecha e izquierda no son", SYSTEM_PROMPT)
        self.assertIn("RX, ultrasonido, TAC y resonancia no son", SYSTEM_PROMPT)
        self.assertIn("cloruro, cloruros y chloride", SYSTEM_PROMPT)
        self.assertIn("No elimines terminaciones de forma general", SYSTEM_PROMPT)

    def test_projection_and_view_are_equivalent_without_losing_count(self):
        three_projections = normalize_text(
            "RAYOS X MANDIBULA 3 PROYECCIONES"
        )
        three_views = normalize_text("RAYOS X MANDIBULA 3 VISTAS")
        four_views = normalize_text("RAYOS X MANDIBULA 4 VISTAS")

        self.assertEqual(three_projections, three_views)
        self.assertNotEqual(three_views, four_views)

    def test_chloride_singular_plural_and_ion_symbol_are_equivalent(self):
        chloride = normalize_text("CHLORIDE")

        self.assertEqual(normalize_text("CLORURO"), chloride)
        self.assertEqual(normalize_text("CLORUROS"), chloride)
        self.assertEqual(normalize_text("CLORURO CL-"), chloride)
        self.assertNotEqual(normalize_text("CLORO"), chloride)

        index = TextCandidateIndex(
            [
                SearchRecord(
                    codigo="82435",
                    nombre="CLORUROS",
                    fuente="catalogo_cpt",
                ),
                SearchRecord(
                    codigo="82310",
                    nombre="CALCIO",
                    fuente="catalogo_cpt",
                ),
            ]
        )

        candidates = index.search("", "CLORURO CL-", limit=2)

        self.assertEqual(candidates[0]["codigo"], "82435")
        self.assertEqual(candidates[0]["scorePreliminar"], 100)

    def test_response_candidates_are_limited_and_filtered(self):
        candidates = [
            {
                "fuente": "medical_fees",
                "codigo": str(70000 + index),
                "nombre": f"CANDIDATO {index}",
                "scorePreliminar": score,
            }
            for index, score in enumerate([99, 82, 75, 60, 45, 44, 30], start=1)
        ]

        result = candidate_models(candidates)

        self.assertEqual(len(result), 5)
        self.assertEqual(
            [candidate.scorePreliminar for candidate in result],
            [99, 82, 75, 60, 45],
        )

    def test_independent_batches_run_with_bounded_concurrency(self):
        client = ConcurrentClient()
        rows = [
            {
                "rowNumber": index,
                "codigoServicio": str(70000 + index),
                "nombreServicio": f"RX ESTUDIO {index}",
            }
            for index in range(1, 5)
        ]
        catalog = [
            {
                "idCptProduct": index,
                "codigoCpt": str(70000 + index),
                "nombreCpt": f"RX ESTUDIO {index}",
                "estado": 1,
            }
            for index in range(1, 5)
        ]
        payload = {
            "rows": rows,
            "catalogoCpt": catalog,
            "catalogoTiposServicio": [
                {
                    "idTipoServicio": 5,
                    "nombreTipoServicio": "Rayos X",
                }
            ],
            "batchSize": 1,
        }

        with patch(
            "proveedores.providerSyncHomologador.pipeline.MAX_BATCH_CONCURRENCY",
            3,
        ):
            response = process_request_payload(
                payload,
                client=client,
                medical_fees_index=TextCandidateIndex([]),
                medical_fees_excel_index=TextCandidateIndex([]),
            )

        self.assertGreaterEqual(client.responses.max_active_calls, 2)
        self.assertLessEqual(client.responses.max_active_calls, 3)
        self.assertEqual(response.tokensUsados, 40)
        self.assertEqual(
            [item.rowNumber for item in response.data.items],
            [1, 2, 3, 4],
        )

    def test_usg_uses_excel_category_to_prioritize_ultrasound(self):
        index = TextCandidateIndex(
            [
                SearchRecord(
                    codigo="93978",
                    nombre="ESTUDIO DE AORTA ABDOMINAL",
                    fuente="medical_fees",
                    categoria="ULTRASONIDOS",
                ),
                SearchRecord(
                    codigo="74175",
                    nombre="ESTUDIO DE AORTA ABDOMINAL",
                    fuente="medical_fees",
                    categoria="TAC",
                ),
            ]
        )

        candidates = index.search("", "USG AORTA ABDOMINAL", limit=2)

        self.assertEqual(candidates[0]["codigo"], "93978")
        self.assertEqual(candidates[0]["categoria"], "ULTRASONIDOS")

    def test_cpt_type_prioritizes_the_compatible_catalog_candidate(self):
        index = TextCandidateIndex(
            [
                SearchRecord(
                    codigo="LAB-01",
                    nombre="PERFIL GENERAL",
                    fuente="catalogo_cpt",
                    id_cpt_product=10,
                    tipo_cpt_id=1,
                    tipo_cpt_nombre="LABORATORIO",
                ),
                SearchRecord(
                    codigo="HOS-01",
                    nombre="PERFIL GENERAL",
                    fuente="catalogo_cpt",
                    id_cpt_product=20,
                    tipo_cpt_id=2,
                    tipo_cpt_nombre="HOSPITALIZACION",
                ),
            ]
        )

        candidates = index.search("", "LABORATORIO PERFIL GENERAL", limit=2)

        self.assertEqual(candidates[0]["idCptProduct"], 10)
        self.assertEqual(candidates[0]["tipoCptNombre"], "LABORATORIO")
        self.assertEqual(candidates[1]["tipoCptNombre"], "HOSPITALIZACION")

    def test_invalid_confidence_label_is_derived_from_percentage(self):
        payload = {
            "rows": [
                {
                    "rowNumber": 2,
                    "codigoServicio": "13.04.13",
                    "nombreServicio": "MAXILAR INFERIOR O SUPERIOR",
                }
            ],
            "catalogoCpt": [
                {
                    "idCptProduct": 99,
                    "codigoCpt": "70100",
                    "nombreCpt": "RAYOS X DE MANDIBULA, MENOS DE 4 VISTAS",
                    "estado": 1,
                }
            ],
            "catalogoTiposServicio": [
                {
                    "idTipoServicio": 7,
                    "nombreTipoServicio": "Rayos X",
                }
            ],
        }

        response = process_request_payload(
            payload,
            client=InvalidConfidenceLabelClient(),
            medical_fees_index=TextCandidateIndex([]),
            medical_fees_excel_index=TextCandidateIndex([]),
        )
        item = response.data.items[0]

        self.assertEqual(item.confianzaPorcentaje, 85)
        self.assertEqual(item.confianza, "alta")
        self.assertFalse(item.requiereRevisionHumana)

    def test_excel_index_keeps_sheet_as_category(self):
        records = load_medical_fees_excel_records()
        rx_record = next(
            record
            for record in records
            if record.codigo == "70100" and record.categoria == "RX"
        )

        self.assertEqual(rx_record.categoria, "RX")
        self.assertIn("MANDIBULA", rx_record.nombre)

    def test_raiza_headers_are_mapped(self):
        text = (
            "PRECIO NEGOCIADO\tFECHA DE INICIO\tOBSERVACIONES\t"
            "CODIGO ASIGNADO RAIZA\tNOMBRE ASIGNADO RAIZA\n"
            "Q200,00\t03/10/2025\t\t13.04.13\tMAXILAR INFERIOR O SUPERIOR\n"
        )
        rows = load_rows_from_delimited_text(text)
        payload = AgentInput.model_validate({"rows": rows})
        parsed = collect_rows(payload)

        self.assertEqual(parsed[0].codigoServicio, "13.04.13")
        self.assertEqual(parsed[0].nombreServicio, "MAXILAR INFERIOR O SUPERIOR")
        self.assertEqual(parsed[0].precio, "Q200,00")
        self.assertEqual(str(parsed[0].fechaInicio), "03/10/2025")

    def test_database_service_type_column_names_are_accepted(self):
        payload = AgentInput.model_validate(
            {
                "rows": [
                    {
                        "codigoServicio": "13.04.20",
                        "nombreServicio": "ORBITAS",
                    }
                ],
                "catalogoTiposServicio": [
                    {
                        "ID_SERVICE_TYPE": 5,
                        "DESCRIPTION": "Rayos X",
                    }
                ],
            }
        )

        service_type = payload.catalogoTiposServicio[0]
        self.assertEqual(service_type.idTipoServicio, 5)
        self.assertEqual(service_type.nombreTipoServicio, "Rayos X")

    def test_medical_fees_page_parser_extracts_base_codes(self):
        page_text = """
        70100 Radiologic examination, mandible; partial, less
        than 4 views
        93 118 162 38 1.17
        70100-26
        43 54 75 9 0.26
        70110 Radiologic examination, mandible; complete,
        minimum of 4 views
        147 185 255 43 1.31
        """
        records = parse_medical_fees_page(page_text, 423)

        self.assertEqual([record.codigo for record in records], ["70100", "70110"])
        self.assertEqual(records[0].pagina_medical_fees, 423)
        self.assertIn("less than 4 views", records[0].nombre)

    def test_response_keeps_row_data_and_verified_catalog_match(self):
        medical_index = TextCandidateIndex(
            [
                SearchRecord(
                    codigo="70100",
                    nombre="Radiologic examination, mandible; partial, less than 4 views",
                    fuente="medical_fees",
                    pagina_medical_fees=423,
                )
            ]
        )
        payload = {
            "fileName": "precios_raiza.xlsx",
            "rows": [
                {
                    "rowNumber": 2,
                    "codigoServicio": "13.04.13",
                    "nombreServicio": "MAXILAR INFERIOR O SUPERIOR",
                    "precio": "Q200,00",
                    "fechaInicio": "03/10/2025",
                    "codigoProveedor": "RAIZA",
                    "nombreProveedor": "RAIZA",
                }
            ],
            "catalogoCpt": [
                {
                    "idCptProduct": 99,
                    "codigoCpt": "70100",
                    "nombreCpt": "RAYOS X DE MANDIBULA, MENOS DE 4 VISTAS",
                    "tipoProcedimientoNombre": "Radiologia",
                    "tipoCptId": 12,
                    "tipoCptNombre": "IMAGENOLOGIA",
                    "estado": 1,
                }
            ],
            "catalogoTiposServicio": [
                {
                    "idTipoServicio": 7,
                    "nombreTipoServicio": "Rayos X",
                }
            ],
        }

        client = FakeClient()
        response = process_request_payload(
            payload,
            client=client,
            medical_fees_index=medical_index,
            medical_fees_excel_index=TextCandidateIndex([]),
        )
        item = response.data.items[0]

        self.assertEqual(item.estadoAsociacion, "asociado")
        self.assertEqual(item.fuenteAsociacion, "catalogo_cpt")
        self.assertEqual(item.idCptProduct, 99)
        self.assertEqual(item.codigoCpt, "70100")
        self.assertEqual(item.tipoCptId, 12)
        self.assertEqual(item.tipoCptNombre, "IMAGENOLOGIA")
        self.assertEqual(item.tipoServicioNombre, "Rayos X")
        self.assertEqual(item.confianzaPorcentaje, 93)
        self.assertEqual(item.precio, "Q200,00")
        self.assertEqual(response.data.resumen.itemsAsociadosCatalogo, 1)
        self.assertEqual(item.codigosCandidatos[0].tipoCptId, 12)
        self.assertEqual(
            item.codigosCandidatos[0].tipoCptNombre,
            "IMAGENOLOGIA",
        )
        system_prompt = client.responses.last_request_args["input"][0]["content"]
        user_prompt = client.responses.last_request_args["input"][1]["content"]
        self.assertEqual(
            client.responses.last_request_args["service_tier"],
            "priority",
        )
        self.assertIn("tipoCptNombre", system_prompt)
        self.assertIn("laboratorio", system_prompt)
        self.assertIn('"tipoCptNombre": "IMAGENOLOGIA"', user_prompt)

    def test_unverified_code_is_rejected_even_with_high_model_confidence(self):
        medical_index = TextCandidateIndex(
            [
                SearchRecord(
                    codigo="70100",
                    nombre="Radiologic examination, mandible; partial, less than 4 views",
                    fuente="medical_fees",
                    pagina_medical_fees=423,
                )
            ]
        )
        payload = {
            "rows": [
                {
                    "rowNumber": 2,
                    "codigoServicio": "13.04.13",
                    "nombreServicio": "MAXILAR INFERIOR O SUPERIOR",
                }
            ],
            "catalogoCpt": [
                {
                    "idCptProduct": 99,
                    "codigoCpt": "70100",
                    "nombreCpt": "RAYOS X DE MANDIBULA, MENOS DE 4 VISTAS",
                    "estado": 1,
                }
            ],
            "catalogoTiposServicio": [
                {
                    "idTipoServicio": 7,
                    "nombreTipoServicio": "Rayos X",
                }
            ],
        }

        response = process_request_payload(
            payload,
            client=InvalidCodeClient(),
            medical_fees_index=medical_index,
            medical_fees_excel_index=TextCandidateIndex([]),
        )
        item = response.data.items[0]

        self.assertEqual(item.estadoAsociacion, "sin_asociacion")
        self.assertEqual(item.fuenteAsociacion, "sin_coincidencia")
        self.assertIsNone(item.codigoCpt)
        self.assertEqual(item.confianzaPorcentaje, 0)
        self.assertTrue(item.requiereRevisionHumana)

    def test_unverified_service_type_requires_human_review(self):
        medical_index = TextCandidateIndex(
            [
                SearchRecord(
                    codigo="70100",
                    nombre="Radiologic examination, mandible; partial, less than 4 views",
                    fuente="medical_fees",
                    pagina_medical_fees=423,
                )
            ]
        )
        payload = {
            "rows": [
                {
                    "rowNumber": 2,
                    "codigoServicio": "13.04.13",
                    "nombreServicio": "MAXILAR INFERIOR O SUPERIOR",
                }
            ],
            "catalogoCpt": [
                {
                    "idCptProduct": 99,
                    "codigoCpt": "70100",
                    "nombreCpt": "RAYOS X DE MANDIBULA, MENOS DE 4 VISTAS",
                    "estado": 1,
                }
            ],
            "catalogoTiposServicio": [
                {
                    "idTipoServicio": 7,
                    "nombreTipoServicio": "Rayos X",
                }
            ],
        }

        response = process_request_payload(
            payload,
            client=InvalidServiceTypeClient(),
            medical_fees_index=medical_index,
            medical_fees_excel_index=TextCandidateIndex([]),
        )
        item = response.data.items[0]

        self.assertEqual(item.estadoAsociacion, "asociado")
        self.assertIsNone(item.tipoServicioId)
        self.assertIsNone(item.tipoServicioNombre)
        self.assertTrue(item.requiereRevisionHumana)

    def test_medical_fees_name_is_returned_in_original_and_spanish(self):
        medical_name = (
            "Radiologic examination, sinuses, paranasal, less than 3 views"
        )
        medical_index = TextCandidateIndex(
            [
                SearchRecord(
                    codigo="70210",
                    nombre=medical_name,
                    fuente="medical_fees",
                    pagina_medical_fees=424,
                )
            ]
        )
        payload = {
            "rows": [
                {
                    "rowNumber": 9,
                    "codigoServicio": "13,04",
                    "nombreServicio": "SENOS PARANASALES",
                }
            ],
            "catalogoTiposServicio": [
                {
                    "idTipoServicio": 5,
                    "nombreTipoServicio": "Rayos X",
                }
            ],
        }

        response = process_request_payload(
            payload,
            client=MedicalTranslationClient(confidence=80),
            medical_fees_index=medical_index,
            medical_fees_excel_index=TextCandidateIndex([]),
        )
        item = response.data.items[0]

        self.assertEqual(item.nombreCptOriginal, medical_name)
        self.assertEqual(
            item.nombreCpt,
            "Examen radiologico de senos paranasales, menos de 3 vistas",
        )
        self.assertFalse(item.requiereRevisionHumana)
        self.assertEqual(response.data.resumen.itemsParaRevision, 0)
        candidate = item.codigosCandidatos[0]
        self.assertEqual(
            candidate.nombre,
            "Examen radiologico de los senos paranasales, menos de 3 vistas",
        )
        self.assertEqual(candidate.nombreOriginal, medical_name)

    def test_items_for_review_only_counts_confidence_below_80(self):
        medical_index = TextCandidateIndex(
            [
                SearchRecord(
                    codigo="70210",
                    nombre=(
                        "Radiologic examination, sinuses, paranasal, "
                        "less than 3 views"
                    ),
                    fuente="medical_fees",
                    pagina_medical_fees=424,
                )
            ]
        )
        payload = {
            "rows": [
                {
                    "rowNumber": 9,
                    "codigoServicio": "13,04",
                    "nombreServicio": "SENOS PARANASALES",
                }
            ],
            "catalogoTiposServicio": [
                {
                    "idTipoServicio": 5,
                    "nombreTipoServicio": "Rayos X",
                }
            ],
        }

        response = process_request_payload(
            payload,
            client=MedicalTranslationClient(confidence=79),
            medical_fees_index=medical_index,
            medical_fees_excel_index=TextCandidateIndex([]),
        )

        self.assertTrue(response.data.items[0].requiereRevisionHumana)
        self.assertEqual(response.data.resumen.itemsParaRevision, 1)

    def test_high_excel_confidence_does_not_consult_pdf(self):
        excel_index = TextCandidateIndex(
            [
                SearchRecord(
                    codigo="701002",
                    nombre=(
                        "RAYOS X DE MANDIBULA / MAXILAR SUPERIOR INFERIOR "
                        "(3 PROYECCIONES)"
                    ),
                    fuente="medical_fees",
                    categoria="RX",
                )
            ]
        )
        client = ExcelFirstClient(initial_confidence=91)
        payload = {
            "rows": [
                {
                    "rowNumber": 2,
                    "codigoServicio": "13.04.61",
                    "nombreServicio": "MANDIBULA 3 VISTAS",
                }
            ],
            "catalogoTiposServicio": [
                {
                    "idTipoServicio": 5,
                    "nombreTipoServicio": "Rayos X",
                }
            ],
        }

        response = process_request_payload(
            payload,
            client=client,
            medical_fees_excel_index=excel_index,
        )
        item = response.data.items[0]

        self.assertEqual(client.responses.calls, 1)
        self.assertEqual(item.codigoCpt, "701002")
        self.assertEqual(item.categoria, "RX")
        self.assertIsNone(item.paginaMedicalFees)

    def test_low_excel_confidence_retries_with_pdf(self):
        excel_index = TextCandidateIndex(
            [
                SearchRecord(
                    codigo="701002",
                    nombre=(
                        "RAYOS X DE MANDIBULA / MAXILAR SUPERIOR INFERIOR "
                        "(3 PROYECCIONES)"
                    ),
                    fuente="medical_fees",
                    categoria="RX",
                )
            ]
        )
        pdf_index = TextCandidateIndex(
            [
                SearchRecord(
                    codigo="70110",
                    nombre=(
                        "Radiologic examination, mandible; complete, "
                        "minimum of 4 views"
                    ),
                    fuente="medical_fees",
                    pagina_medical_fees=423,
                )
            ]
        )
        client = ExcelFirstClient(initial_confidence=72)
        payload = {
            "rows": [
                {
                    "rowNumber": 2,
                    "codigoServicio": "13.04.61",
                    "nombreServicio": "MANDIBULA 3 VISTAS",
                }
            ],
            "catalogoTiposServicio": [
                {
                    "idTipoServicio": 5,
                    "nombreTipoServicio": "Rayos X",
                }
            ],
        }

        response = process_request_payload(
            payload,
            client=client,
            medical_fees_index=pdf_index,
            medical_fees_excel_index=excel_index,
        )
        item = response.data.items[0]

        self.assertEqual(client.responses.calls, 2)
        self.assertEqual(item.codigoCpt, "70110")
        self.assertIsNone(item.categoria)
        self.assertEqual(item.paginaMedicalFees, 423)
        self.assertEqual(item.confianzaPorcentaje, 94)


if __name__ == "__main__":
    unittest.main()
