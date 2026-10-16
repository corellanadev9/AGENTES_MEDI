import json
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from agentAuditoriaMedica.pipeline import (
    _canonical_url,
    _patient_age,
    process_request_payload,
    project_clinical_data,
)


SOURCE = "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=example"


class FakeResponse:
    status = "completed"
    usage = SimpleNamespace(total_tokens=123)

    def __init__(self, findings, *, searched=True, source=SOURCE):
        self.output_text = json.dumps({"hallazgos": findings})
        self._output = []
        if searched:
            self._output.append({
                "type": "web_search_call",
                "action": {"sources": [{"url": source, "title": "Ficha oficial"}]},
            })

    def model_dump(self):
        return {"output": self._output}


class FakeClient:
    def __init__(self, *responses):
        self._responses = responses
        self.responses = self
        self.arguments = None
        self.calls = []

    def create(self, **kwargs):
        self.arguments = kwargs
        self.calls.append(kwargs)
        return self._responses[min(len(self.calls) - 1, len(self._responses) - 1)]


def payload():
    return {
        "internalCode": 700,
        "data": {
            "carneCompleto": "IDENTIFICADOR_SECRETO",
            "codigoSolicitud": 123,
            "edad": 49,
            "fechaNacimiento": "1976-12-23",
            "fechaServicio": "2013-11-08",
            "nombreProveedor": "NOMBRE_PROVEEDOR_SECRETO",
            "diagnosticos": [{
                "codigoDiagnostico": "789.09", "icd": 9,
                "nombreDiagnostico": "Dolor abdominal", "nombrePaciente": "PACIENTE_SECRETO",
            }],
            "medicamentos": [{
                "compuestoActivo": "principio activo", "descripcionMedicamento": "Fármaco A",
                "dosis": "1 tableta", "frecuencia": "24 horas", "codigoPaciente": "PACIENTE_SECRETO",
            }],
            "procedimientos": [{
                "nombreProcedimiento": "Hemograma", "tipoProcedimiento": "Laboratorio",
                "direccion": "DIRECCION_SECRETA",
            }],
        },
    }


def finding(item_id, url=SOURCE, juicio="compatible"):
    return {
        "idItem": item_id,
        "juicio": juicio,
        "prioridad": "media" if juicio == "alerta" else "ninguna",
        "fundamentoClinico": "Requiere cotejo con indicación documentada.",
        "informacionFaltante": ["Indicación documentada"],
        "fuentes": [url],
    }


class AuditoriaMedicaTests(unittest.TestCase):
    def setUp(self):
        clock = patch("agentAuditoriaMedica.pipeline._today_guatemala", return_value=date(2026, 9, 24))
        clock.start()
        self.addCleanup(clock.stop)

    def test_projection_uses_birthdate_for_age_and_only_medicines(self):
        projected = project_clinical_data(payload())
        encoded = json.dumps(projected, ensure_ascii=False)
        for secret in (
            "IDENTIFICADOR_SECRETO", "PACIENTE_SECRETO", "NOMBRE_PROVEEDOR_SECRETO",
            "DIRECCION_SECRETA", "fechaServicio", "fechaNacimiento", "1976-12-23",
            "2013-11-08", "codigoSolicitud", "Hemograma",
        ):
            self.assertNotIn(secret, encoded)
        self.assertEqual(set(projected), {"edad", "diagnosticos", "medicamentos"})
        self.assertEqual(projected["edad"], 49)
        self.assertEqual([item["tipo"] for item in projected["medicamentos"]],
                         ["medicamento"])

    def test_birthdate_takes_precedence_and_reported_age_is_fallback(self):
        request = payload()
        request["data"]["edad"] = 36
        request["data"]["fechaServicio"] = "2013-11-08"
        self.assertEqual(project_clinical_data(request)["edad"], 49)
        request["data"].pop("fechaNacimiento")
        self.assertEqual(project_clinical_data(request)["edad"], 36)
        request["data"].pop("edad")
        with self.assertRaises(ValueError):
            project_clinical_data(request)

    def test_birthdate_boundary_and_invalid_date(self):
        request = {"fechaNacimiento": "1976-12-23"}
        self.assertEqual(_patient_age(request, date(2026, 12, 22)), 49)
        self.assertEqual(_patient_age(request, date(2026, 12, 23)), 50)
        with self.assertRaises(ValueError):
            _patient_age({"fechaNacimiento": "1976-13-23"}, date(2026, 9, 24))

    def test_accepts_only_age_diagnoses_and_medicines(self):
        projected = project_clinical_data({"data": {
            "edad": 49,
            "diagnosticos": [{"nombreDiagnostico": "Dolor abdominal"}],
            "medicamentos": [{"descripcionMedicamento": "Medicamento A"}],
        }})
        self.assertEqual(set(projected), {"edad", "diagnosticos", "medicamentos"})
        self.assertEqual(projected["edad"], 49)
        self.assertEqual(projected["medicamentos"][0]["idItem"], "M1")

    def test_uses_requested_model_and_returns_verified_sources(self):
        client = FakeClient(FakeResponse([finding("M1", juicio="alerta")]))
        result = process_request_payload(payload(), client=client)
        args = client.arguments
        self.assertEqual(args["model"], "gpt-6-luna")
        self.assertEqual(args["reasoning"], {"effort": "medium"})
        self.assertEqual(args["text"]["verbosity"], "medium")
        self.assertEqual(args["tool_choice"], "required")
        self.assertFalse(args["store"])
        self.assertNotIn("PACIENTE_SECRETO", json.dumps(args["input"]))
        self.assertNotIn("1976-12-23", json.dumps(args["input"]))
        self.assertNotIn("Hemograma", json.dumps(args["input"]))
        self.assertIn('"edad":49', args["input"][1]["content"])
        self.assertEqual(result["data"]["estadoAuditoria"], "requiere_revision_clinica")
        self.assertEqual(result["data"]["evaluacionMedicaAutorizacion"], "objeciones_clinicas")
        self.assertEqual(result["versionContrato"], "2.2")
        self.assertEqual(len(client.calls), 1)
        self.assertNotIn("autorizacionCorrecta", result["data"])
        self.assertEqual(result["data"]["datosEvaluados"], project_clinical_data(payload()))
        self.assertNotIn("PACIENTE_SECRETO", json.dumps(result, ensure_ascii=False))
        self.assertNotIn("póliza", json.dumps(result, ensure_ascii=False).lower())
        self.assertNotIn("expediente", json.dumps(result, ensure_ascii=False).lower())
        self.assertEqual(result["data"]["hallazgos"][0]["fuentes"][0]["url"], SOURCE)
        self.assertTrue(result["data"]["hallazgos"][0]["requiereRevisionClinicaAdicional"])
        self.assertNotIn("requiereRevisionHumana", result["data"]["hallazgos"][0])

    def test_unverified_or_missing_web_evidence_is_insufficient(self):
        client = FakeClient(FakeResponse([
            finding("M1", "https://example.com/imaginary"),
        ]))
        result = process_request_payload(payload(), client=client)
        self.assertEqual(result["data"]["estadoAuditoria"], "evidencia_insuficiente")
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(result["data"]["hallazgos"][0]["prioridad"], "ninguna")
        self.assertTrue(result["data"]["hallazgos"][0]["requiereRevisionClinicaAdicional"])
        self.assertEqual(result["data"]["evaluacionMedicaAutorizacion"], "indeterminada")
        self.assertTrue(all(item["juicio"] == "insuficiente"
                            for item in result["data"]["hallazgos"]))
        client = FakeClient(FakeResponse([finding("M1")], searched=False))
        result = process_request_payload(payload(), client=client)
        self.assertEqual(result["data"]["resumen"]["insuficiente"], 1)

    def test_targeted_second_search_recovers_missing_source(self):
        first = FakeResponse([finding("M1", "https://example.com/imaginary")])
        second = FakeResponse([finding("M1")])
        client = FakeClient(first, second)
        result = process_request_payload(payload(), client=client)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[1]["tools"][0]["search_context_size"], "high")
        self.assertEqual(client.calls[1]["timeout"], 75.0)
        self.assertEqual(result["tokensUsados"], 246)
        self.assertEqual(result["data"]["hallazgos"][0]["juicio"], "compatible")
        self.assertEqual(result["data"]["hallazgos"][0]["fuentes"][0]["url"], SOURCE)

    def test_second_review_can_resolve_an_insufficient_judgment(self):
        client = FakeClient(
            FakeResponse([finding("M1", juicio="insuficiente")]),
            FakeResponse([finding("M1", juicio="alerta")]),
        )
        result = process_request_payload(payload(), client=client)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(result["data"]["hallazgos"][0]["juicio"], "alerta")
        self.assertEqual(result["data"]["evaluacionMedicaAutorizacion"], "objeciones_clinicas")

    def test_markdown_source_url_matches_searched_source(self):
        markdown = f"[{SOURCE}]({SOURCE}&utm_source=openai)"
        client = FakeClient(FakeResponse([finding("M1", markdown)], source=SOURCE))
        result = process_request_payload(payload(), client=client)
        self.assertEqual(result["data"]["hallazgos"][0]["juicio"], "compatible")
        self.assertEqual(result["data"]["evaluacionMedicaAutorizacion"], "congruente_con_datos")
        self.assertEqual(result["data"]["hallazgos"][0]["fuentes"][0]["url"], SOURCE)
        self.assertFalse(result["data"]["hallazgos"][0]["requiereRevisionClinicaAdicional"])

    def test_compatible_count_does_not_hide_other_medicines_needing_review(self):
        request = {"data": {"edad": 30,
            "diagnosticos": [{"nombreDiagnostico": "Gastroenteritis"}],
            "medicamentos": [{"descripcionMedicamento": f"Medicamento {i}"} for i in range(1, 5)]}}
        first = FakeResponse([finding("M1"), finding("M2", juicio="insuficiente"),
                              finding("M3", juicio="insuficiente"), finding("M4", juicio="alerta")])
        second = FakeResponse([finding("M2", juicio="insuficiente"),
                               finding("M3", juicio="insuficiente")])
        result = process_request_payload(request, client=FakeClient(first, second))
        summary = result["data"]["resumen"]
        self.assertEqual(summary["compatible"], 1)
        self.assertEqual(summary["requierenRevisionClinicaAdicional"], 3)
        self.assertEqual(result["data"]["estadoAuditoria"], "requiere_revision_clinica")
        self.assertEqual(
            [item["requiereRevisionClinicaAdicional"] for item in result["data"]["hallazgos"]],
            [False, True, True, True],
        )

    def test_rejects_mismatched_findings_and_unsafe_urls(self):
        client = FakeClient(FakeResponse([finding("M2")]))
        with self.assertRaises(RuntimeError):
            process_request_payload(payload(), client=client)
        self.assertIsNone(_canonical_url("https://fda.gov.evil.example/label"))
        self.assertIsNone(_canonical_url("http://fda.gov/label"))

    def test_requires_diagnoses_and_items(self):
        with self.assertRaises(ValueError):
            project_clinical_data({"data": {"medicamentos": [{"descripcionMedicamento": "A"}]}})
        with self.assertRaises(ValueError):
            project_clinical_data({"data": {"diagnosticos": [{"nombreDiagnostico": "Dolor"}], "edad": 49}})


if __name__ == "__main__":
    unittest.main()
