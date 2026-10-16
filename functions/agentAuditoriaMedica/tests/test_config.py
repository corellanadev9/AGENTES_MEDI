import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentAuditoriaMedica import config


class LocalEnvTests(unittest.TestCase):
    def test_loads_local_keys_without_overriding_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "OPENAI_API_KEY=sk-local-test\n"
                "IGNORED_SECRET=never-load\n", encoding="utf-8"
            )
            with patch.object(config, "ENV_FILE", env_file):
                with patch.dict(os.environ, {"OPENAI_API_KEY": "existing-key"}, clear=True):
                    config.load_local_env()
                    self.assertEqual(os.environ["OPENAI_API_KEY"], "existing-key")
                    self.assertNotIn("AUDITORIA_MEDICA_TOKEN", os.environ)
                    self.assertNotIn("IGNORED_SECRET", os.environ)


if __name__ == "__main__":
    unittest.main()
