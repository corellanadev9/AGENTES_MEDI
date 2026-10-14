import json
import unittest
from types import SimpleNamespace

from proveedores.providerSyncDoctorPlusPrices.pipeline import process_request_payload
from proveedores.providerSyncHomologador.matching import SearchRecord, TextCandidateIndex


class FakeResponses:
    def __init__(self, output):
        self.output = output

    def create(self, **kwargs):
        return SimpleNamespace(
            output_text=json.dumps(self.output),
            usage=SimpleNamespace(total_tokens=25),
        )


class FakeClient:
    def __init__(self, output):
        self.responses = FakeResponses(output)


class DoctorPlusPriceAgentTests(unittest.TestCase):
    def setUp(self):
        self.index = TextCandidateIndex(
            [
                SearchRecord(
                    codigo="70100",
                    nombre="Radiologic examination, mandible; partial, less than 4 views",
                    fuente="medical_fees",
                    categoria="Radiology",
                )
            ]
        )

    def test_accepts_only_verified_medical_fees_code(self):
        client = FakeClient(
            {
                "items": [
                    {
                        "rowNumber": 1,
                        "estadoAsociacion": "asociado",
                        "codigoProviderSync": "70100",
                        "servicePsDescription": "texto libre del modelo que debe ignorarse",
                        "confianzaPorcentaje": 94,
                        "motivo": "Anatomia y modalidad compatibles.",
                    }
                ]
            }
        )
        response = process_request_payload(
            {
                "rows": [
                    {
                        "rowNumber": 1,
                        "codigoServicio": "701001",
                        "nombreServicio": "MAXILAR INFERIOR O SUPERIOR",
                    }
                ]
            },
            client=client,
            medical_fees_excel_index=self.index,
        )
        item = response.data.items[0]
        self.assertEqual(item.estadoAsociacion, "asociado")
        self.assertEqual(item.codigoProviderSync, "70100")
        self.assertEqual(
            item.servicePsDescription,
            "Radiologic examination, mandible; partial, less than 4 views",
        )
        self.assertEqual(item.servicePsDescription, item.nombreMedicalFees)
        self.assertFalse(item.requiereRevisionHumana)

        serialized_item = response.model_dump(mode="json", exclude_none=True)[
            "data"
        ]["items"][0]
        self.assertEqual(
            serialized_item["servicePsDescription"],
            "Radiologic examination, mandible; partial, less than 4 views",
        )

    def test_rejects_code_not_present_in_verified_candidates(self):
        client = FakeClient(
            {
                "items": [
                    {
                        "rowNumber": 1,
                        "estadoAsociacion": "asociado",
                        "codigoProviderSync": "99999",
                        "confianzaPorcentaje": 99,
                        "motivo": "Inventado",
                    }
                ]
            }
        )
        response = process_request_payload(
            {
                "rows": [
                    {
                        "rowNumber": 1,
                        "codigoServicio": "ABC",
                        "nombreServicio": "MAXILAR INFERIOR",
                    }
                ]
            },
            client=client,
            medical_fees_excel_index=self.index,
        )
        item = response.data.items[0]
        self.assertEqual(item.estadoAsociacion, "sin_asociacion")
        self.assertIsNone(item.codigoProviderSync)
        self.assertIsNone(item.servicePsDescription)

        serialized_item = response.model_dump(mode="json", exclude_none=True)[
            "data"
        ]["items"][0]
        self.assertNotIn("servicePsDescription", serialized_item)

    def test_limits_request_to_two_hundred_rows(self):
        with self.assertRaises(ValueError):
            process_request_payload(
                {
                    "rows": [
                        {
                            "rowNumber": index,
                            "codigoServicio": str(index),
                            "nombreServicio": "ESTUDIO",
                        }
                        for index in range(1, 202)
                    ]
                },
                client=FakeClient({"items": []}),
                medical_fees_excel_index=self.index,
            )


if __name__ == "__main__":
    unittest.main()
