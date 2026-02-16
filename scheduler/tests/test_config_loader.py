import os
import tempfile
import unittest
from pathlib import Path

from scheduler.config_loader import load_yaml_config


class ConfigLoaderTest(unittest.TestCase):
    def test_load_yaml_config_resolves_env_and_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(
                """
email:
  sender: "${SMTP_SENDER}"
  recipient: "${SMTP_RECIPIENT:default@example.com}"
""".strip(),
                encoding="utf-8",
            )

            os.environ["SMTP_SENDER"] = "signal@example.com"
            os.environ.pop("SMTP_RECIPIENT", None)

            config = load_yaml_config(config_path)

            self.assertEqual(config["email"]["sender"], "signal@example.com")
            self.assertEqual(config["email"]["recipient"], "default@example.com")


if __name__ == "__main__":
    unittest.main()
