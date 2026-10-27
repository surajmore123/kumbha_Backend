"""The reply language follows the user's question, not the app setting."""

from unittest import mock

from django.test import SimpleTestCase

from apps.aiChat import messages
from apps.aiChat.services.transcription_service import Transcript
from apps.aiChat.tests.helpers import GuruTestCase, make_event, png_bytes, upload, wav_bytes


class DetectionTests(SimpleTestCase):
    def check(self, text, code, app="", romanized=False, explicit=False, source=None):
        info = messages.analyze_language(text, app)
        self.assertEqual(info.code, code, text)
        self.assertEqual(info.romanized, romanized, text)
        self.assertEqual(info.explicit, explicit, text)
        if source:
            self.assertEqual(info.source, source, text)

    def test_question_language_beats_app_language(self):
        self.check("पुढचे अमृत स्नान कधी आहे?", "mr", app="en")
        self.check("अगला अमृत स्नान कब है?", "hi", app="mr")
        self.check("When is the next Amrit Snan?", "en", app="mr")

    def test_hindi_and_marathi_are_told_apart(self):
        self.check("काळाराम मंदिर", "mr", app="hi")          # ळ is Marathi
        self.check("रामकुंड येथे गर्दी आहे का?", "mr")
        self.check("रामकुंड पर भीड़ है क्या?", "hi")
        self.check("त्र्यंबकेश्वर", "mr", app="mr")          # no signal: app decides
        self.check("त्र्यंबकेश्वर", "hi", app="en")          # no signal, no Devanagari app: Hindi

    def test_other_indian_scripts(self):
        self.check("આગામી અમૃત સ્નાન ક્યારે છે?", "gu")
        self.check("அடுத்த அம்ருத் ஸ்நான் எப்போது?", "ta")
        self.check("తదుపరి అమృత్ స్నాన్ ఎప్పుడు?", "te")
        self.check("ਅਗਲਾ ਅੰਮ੍ਰਿਤ ਇਸ਼ਨਾਨ ਕਦੋਂ ਹੈ?", "pa")
        self.check("পরবর্তী অমৃত স্নান কবে?", "bn")
        self.check("ಮುಂದಿನ ಅಮೃತ ಸ್ನಾನ ಯಾವಾಗ?", "kn")
        self.check("അടുത്ത അമൃത് സ്നാൻ എപ്പോഴാണ്?", "ml")
        self.check("اگلا امرت اسنان کب ہے؟", "ur")

    def test_romanized_hindi_and_marathi(self):
        self.check("Amrit snan kab hai?", "hi", app="en", romanized=True)
        self.check("Ramkund la gardi aahe ka?", "mr", app="en", romanized=True)
        self.check("pudhcha snan kadhi aahe", "mr", romanized=True)

    def test_explicit_request_wins(self):
        self.check("Explain this document in Hindi", "hi", app="en", explicit=True)
        self.check("Tell me about Ramkund in Marathi please", "mr", explicit=True)
        self.check("हे इंग्रजीत सांगा", "en", explicit=True)
        self.check("कृपया मराठी में बताइए", "mr", explicit=True)

    def test_no_language_signal_uses_app_language(self):
        self.check("", "mr", app="mr", source="app")
        self.check("Ramkund?", "hi", app="hi", source="app")
        self.check("", "en", source="default")


class ReplyLanguageTests(GuruTestCase):
    def test_marathi_question_in_english_app_gets_marathi_answer(self):
        model = self.mock_model("रामकुंड हा मुख्य घाट आहे.")
        reply = self.reply(self.send("मला एक छोटी प्रार्थना सांगा", language="en"))
        self.assertEqual(reply["metadata"]["language"], "mr")
        self.assertIn("The user wrote in Marathi. Reply entirely in Marathi", self.system_prompt(model))

    def test_english_question_in_marathi_app_gets_english_answer(self):
        model = self.mock_model("ok")
        reply = self.reply(self.send("What should I pack for a long trip?", language="mr"))
        self.assertEqual(reply["metadata"]["language"], "en")
        self.assertIn("Reply entirely in English", self.system_prompt(model))

    def test_hindi_fixed_reply_without_model(self):
        model = self.mock_model()
        reply = self.reply(self.send("अगला कार्यक्रम कब है?", language="en"))
        self.assertEqual(reply["metadata"]["language"], "hi")
        self.assertIn("कोई आगामी", reply["content"])
        model.assert_not_called()

    def test_romanized_hindi_is_answered_in_latin_script(self):
        model = self.mock_model("Agla Amrit Snan ...")
        make_event("Amrit Snan One")
        reply = self.reply(self.send("Agla Amrit snan kab hai?"))
        self.assertEqual(reply["metadata"]["route"], "events")
        self.assertIn("written in Latin letters", self.system_prompt(model))

    def test_explicit_language_request(self):
        model = self.mock_model("ok")
        self.send("Write a short birthday wish in Marathi")
        self.assertIn("The user asked for the answer in Marathi", self.system_prompt(model))

    def test_photo_without_caption_uses_app_language(self):
        model = self.mock_model("ok")
        reply = self.reply(self.send(file=upload("p.png", png_bytes(), "image/png"), language="mr"))
        self.assertEqual(reply["metadata"]["language"], "mr")
        self.assertIn("Reply in Marathi, the user's app language", self.system_prompt(model))

    def test_spoken_language_beats_app_language(self):
        model = self.mock_model("ok")
        make_event()
        with mock.patch(
            "apps.aiChat.graph.transcribe_audio",
            return_value=Transcript(True, "mr", "पुढचे अमृत स्नान कधी आहे?"),
        ):
            reply = self.reply(self.send(file=upload("v.wav", wav_bytes(), "audio/wav"), language="en"))
        self.assertEqual(reply["metadata"]["language"], "mr")
        self.assertEqual(reply["metadata"]["route"], "events")
        self.assertIn("Reply entirely in Marathi", self.system_prompt(model))

    def test_gujarati_question_reaches_the_tools_and_is_answered_in_gujarati(self):
        model = self.mock_model("આગામી અમૃત સ્નાન ...")
        event = make_event("Amrit Snan One")
        with mock.patch(
            "apps.aiChat.graph.english_for_search",
            return_value="When is the next Amrit Snan?",
        ) as translate:
            reply = self.reply(self.send("આગામી અમૃત સ્નાન ક્યારે છે?", language="en"))
        translate.assert_called_once()
        self.assertEqual(reply["metadata"]["language"], "gu")
        self.assertEqual(reply["metadata"]["route"], "events")
        self.assertEqual(reply["metadata"]["events"][0]["id"], str(event.event_id))
        self.assertIn("Reply entirely in Gujarati", self.system_prompt(model))
        # The original question is what gets answered.
        self.assertIn("આગામી અમૃત સ્નાન ક્યારે છે?", self.prompt_text(model))

    def test_fixed_reply_is_translated_for_other_languages(self):
        model = self.mock_model()
        with mock.patch(
            "apps.aiChat.graph.english_for_search", return_value="What are the upcoming events?",
        ), mock.patch(
            "apps.aiChat.services.language_service.invoke_gemini",
            return_value="ઉપલબ્ધ ડેટાબેઝમાં કોઈ આગામી કાર્યક્રમ મળ્યો નથી.",
        ) as translate:
            reply = self.reply(self.send("આગામી કાર્યક્રમો કયા છે?"))
        self.assertIn("આગામી કાર્યક્રમ", reply["content"])
        self.assertIn("Gujarati", translate.call_args.args[0][0]["text"])
        model.assert_not_called()

    def test_failed_translation_falls_back_to_english_text(self):
        from apps.aiChat.services.gemini_service import GeminiQuotaError

        self.mock_model()
        with mock.patch(
            "apps.aiChat.graph.english_for_search", return_value=None,
        ), mock.patch(
            "apps.aiChat.services.language_service.invoke_gemini",
            side_effect=GeminiQuotaError("429"),
        ):
            reply = self.reply(self.send("આગામી કાર્યક્રમો કયા છે? event"))
        self.assertIn("couldn't find any upcoming", reply["content"])
