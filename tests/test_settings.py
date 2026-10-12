import unittest

from config.settings import DEFAULT_SETTINGS, SETTINGS_FILE, load_settings


class SettingsTests(unittest.TestCase):
    def test_settings_toml_is_loaded_and_merged(self):
        settings = load_settings(SETTINGS_FILE)
        self.assertEqual(settings["llm"]["tool_mode"], "auto")
        self.assertIn("rag_service", settings)

    def test_default_persona_identifies_as_helium(self):
        self.assertIn("Helium", DEFAULT_SETTINGS["assistant"]["persona"])

    def test_voice_and_embedding_settings_are_gone(self):
        settings = load_settings(SETTINGS_FILE)
        self.assertNotIn("wake_word", settings)
        self.assertNotIn("speech", settings)
        self.assertNotIn("embedding_model", settings["rag_service"])


if __name__ == "__main__":
    unittest.main()
