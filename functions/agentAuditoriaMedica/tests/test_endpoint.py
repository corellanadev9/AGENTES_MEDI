import unittest
from unittest.mock import patch

from flask import Flask, request

import main


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def test_deployment_is_public_without_firebase_secrets(self):
        manifest = main.auditoria_medica_api.__firebase_endpoint__
        self.assertEqual(manifest.httpsTrigger, {"invoker": ["public"]})
        self.assertEqual(manifest.secretEnvironmentVariables, [])

    def test_accepts_json_without_authentication(self):
        with patch.object(main, "auditoria_medica_handler", return_value={"data": {}}) as handler:
            with self.app.test_request_context(
                "/", method="POST", data='{"data":{"diagnosticos":[]}}',
                content_type="application/json",
            ):
                response = main.auditoria_medica_api(request)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["agent"], "agentAuditoriaMedica")
            handler.assert_called_once()

    def test_rejects_non_json_without_calling_agent(self):
        with patch.object(main, "auditoria_medica_handler") as handler:
            with self.app.test_request_context("/", method="POST", data="not-json"):
                response = main.auditoria_medica_api(request)
            self.assertEqual(response.status_code, 400)
            handler.assert_not_called()


if __name__ == "__main__":
    unittest.main()
