import unittest
from pydantic import ValidationError

from models.tts import (
    AssistantVoicePreference,
    AssistantVoicePreferenceUpdate,
    TtsSynthesizeRequest,
    TtsVoice,
    TtsVoiceCatalog,
    TtsVoiceSettings,
)


class TestTtsModelValidation(unittest.TestCase):
    def test_tts_voice_settings_valid(self):
        settings = TtsVoiceSettings(
            stability=0.5,
            similarity_boost=0.75,
            style=0.2,
            use_speaker_boost=True,
        )
        self.assertEqual(settings.stability, 0.5)
        self.assertEqual(settings.similarity_boost, 0.75)
        self.assertEqual(settings.style, 0.2)
        self.assertTrue(settings.use_speaker_boost)

    def test_tts_voice_settings_bounds_rejected(self):
        with self.assertRaises(ValidationError):
            TtsVoiceSettings(stability=-0.1)

        with self.assertRaises(ValidationError):
            TtsVoiceSettings(stability=1.1)

        with self.assertRaises(ValidationError):
            TtsVoiceSettings(similarity_boost=-0.5)

        with self.assertRaises(ValidationError):
            TtsVoiceSettings(similarity_boost=1.5)

        with self.assertRaises(ValidationError):
            TtsVoiceSettings(style=-0.1)

        with self.assertRaises(ValidationError):
            TtsVoiceSettings(style=1.1)

    def test_tts_synthesize_request_valid(self):
        req = TtsSynthesizeRequest(
            text="  Hello, world!  ",
            voice_id="  voice_123  ",
            model_id="  model_abc  ",
            output_format="  mp3_44100_128  ",
        )
        self.assertEqual(req.text, "Hello, world!")
        self.assertEqual(req.voice_id, "voice_123")
        self.assertEqual(req.model_id, "model_abc")
        self.assertEqual(req.output_format, "mp3_44100_128")

    def test_tts_synthesize_request_blank_text_rejected(self):
        with self.assertRaises(ValidationError):
            TtsSynthesizeRequest(text="    ")

    def test_tts_synthesize_request_non_string_text_rejected(self):
        with self.assertRaises(ValidationError):
            TtsSynthesizeRequest(text=123)

    def test_tts_synthesize_request_blank_voice_id_rejected(self):
        with self.assertRaises(ValidationError):
            TtsSynthesizeRequest(text="Hello", voice_id="   ")

    def test_tts_synthesize_request_non_string_voice_id_rejected(self):
        with self.assertRaises(ValidationError):
            TtsSynthesizeRequest(text="Hello", voice_id=123)

    def test_assistant_voice_preference_valid(self):
        pref = AssistantVoicePreference(voice_id="  custom_voice  ")
        self.assertEqual(pref.voice_id, "custom_voice")

    def test_assistant_voice_preference_blank_rejected(self):
        with self.assertRaises(ValidationError):
            AssistantVoicePreference(voice_id="   ")

    def test_assistant_voice_preference_non_string_rejected(self):
        with self.assertRaises(ValidationError):
            AssistantVoicePreference(voice_id=123)

    def test_assistant_voice_preference_update_valid(self):
        up = AssistantVoicePreferenceUpdate(voice_id="  new_voice  ")
        self.assertEqual(up.voice_id, "new_voice")

    def test_assistant_voice_preference_update_blank_rejected(self):
        with self.assertRaises(ValidationError):
            AssistantVoicePreferenceUpdate(voice_id="   ")

    def test_assistant_voice_preference_update_non_string_rejected(self):
        with self.assertRaises(ValidationError):
            AssistantVoicePreferenceUpdate(voice_id=123)

    def test_tts_voice_catalog_valid(self):
        v = TtsVoice(id="  v1  ", name="  Sloane  ")
        cat = TtsVoiceCatalog(voices=[v], default_voice_id="  v1  ")
        self.assertEqual(v.id, "v1")
        self.assertEqual(v.name, "Sloane")
        self.assertEqual(cat.default_voice_id, "v1")


if __name__ == "__main__":
    unittest.main()
