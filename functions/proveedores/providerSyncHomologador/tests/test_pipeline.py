import json
import unittest
from types import SimpleNamespace

from proveedores.providerSyncHomologador.matching import SearchRecord, TextCandidateIndex
from proveedores.providerSyncHomologador.medical_fees import parse_medical_fees_page
from proveedores.providerSyncHomologador.medical_fees_excel import (
    load_medical_fees_excel_records,
)
from proveedores.providerSyncHomologador.pipeline import (
    collect_rows,
    load_rows_from_delimited_text,
    process_request_payload,
)
from proveedores.providerSyncHomologador.schemas import AgentInput


class FakeResponses:
    def create(self, **request_args):
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


class ProviderSyncHomologadorTests(unittest.TestCase):
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
            client=FakeClient(),
            medical_fees_index=medical_index,
            medical_fees_excel_index=TextCandidateIndex([]),
        )
        item = response.data.items[0]

        self.assertEqual(item.estadoAsociacion, "asociado")
        self.assertEqual(item.fuenteAsociacion, "catalogo_cpt")
        self.assertEqual(item.idCptProduct, 99)
        self.assertEqual(item.codigoCpt, "70100")
        self.assertEqual(item.tipoServicioNombre, "Rayos X")
        self.assertEqual(item.confianzaPorcentaje, 93)
        self.assertEqual(item.precio, "Q200,00")
        self.assertEqual(response.data.resumen.itemsAsociadosCatalogo, 1)

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
