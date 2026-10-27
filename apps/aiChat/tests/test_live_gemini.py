"""
Live provider checks. Skipped unless explicitly enabled:

    RUN_LIVE_AI_TESTS=1 python manage.py test apps.aiChat.tests.test_live_gemini

They use GEMINI_API_KEY from the environment and make about six small
calls (text, image, PDF OCR, TTS, transcription of the TTS output).
"""

import io
import os
import unittest
from unittest import mock

from django.test import SimpleTestCase, TestCase
from PIL import Image, ImageDraw

from apps.aiChat.services import ocr_service, transcription_service, voice_service
from apps.aiChat.services.gemini_service import invoke_gemini
from apps.aiChat.tests.helpers import make_event, pdf_bytes, upload

LIVE = os.getenv("RUN_LIVE_AI_TESTS") == "1" and bool(os.getenv("GEMINI_API_KEY"))


@unittest.skipUnless(LIVE, "set RUN_LIVE_AI_TESTS=1 to call the real Gemini API")
class LiveGeminiTests(SimpleTestCase):
    def test_text(self):
        reply = invoke_gemini("Reply with exactly the word: pong")
        self.assertIn("pong", reply.lower())

    def test_image_bytes_reach_the_model(self):
        import base64

        image = Image.new("RGB", (160, 160), (255, 255, 255))
        ImageDraw.Draw(image).rectangle((40, 40, 120, 120), fill=(220, 0, 0))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        reply = invoke_gemini([
            {"type": "text", "text": "What colour is the square? Answer with one word."},
            {"type": "image", "base64": base64.b64encode(buffer.getvalue()).decode(),
             "mime_type": "image/png"},
        ])
        self.assertIn("red", reply.lower())

    def test_scanned_pdf_ocr(self):
        image = Image.new("RGB", (900, 300), (255, 255, 255))
        ImageDraw.Draw(image).text((40, 120), "GATE 7 OPENS AT 5 AM", fill=(0, 0, 0))
        image = image.resize((1800, 600))
        buffer = io.BytesIO()
        image.save(buffer, format="PDF")
        pages = ocr_service.ocr_pdf(buffer.getvalue())
        text = " ".join(p.get("text", "") for p in pages).upper()
        self.assertIn("GATE 7", text)

    def test_tts_then_transcription_unit(self):
        wav = voice_service.synthesize_speech("Where is the Ramkund ghat?")
        self.assertTrue(wav.startswith(b"RIFF"))
        heard = transcription_service.transcribe_audio(wav, "audio/wav")
        self.assertTrue(heard.speech_detected)
        self.assertIn("ramkund", heard.text.lower().replace(" ", ""))


@unittest.skipUnless(LIVE, "set RUN_LIVE_AI_TESTS=1 to call the real Gemini API")
class LiveEndToEndTests(TestCase):
    """The real HTTP endpoint, database tools and graph, with live Gemini."""

    def setUp(self):
        import shutil
        import tempfile

        from django.core.cache import cache
        from django.test import override_settings
        from rest_framework.test import APIClient

        from apps.authentication.models import User

        cache.clear()
        media = tempfile.mkdtemp(prefix="guru_live_")
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)
        # The local knowledge store isn't used here.
        patcher = mock.patch("apps.aiChat.graph.search_documents", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)

        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user(phone_number="9111111111"))

    def _send(self, **data):
        response = self.client.post("/api/chat/chat-send/", data, format="multipart")
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()["data"]["messages"][1]

    def test_voice_question_answered_from_event_records(self):
        make_event("Live Test Amrit Snan", days=20)
        # LIVE_TEST_SPEECH_WAV: a recording of "When is the next Amrit Snan?"
        # (avoids spending the TTS quota); otherwise Gemini TTS makes one.
        recording = os.getenv("LIVE_TEST_SPEECH_WAV")
        if recording:
            with open(recording, "rb") as handle:
                wav = handle.read()
        else:
            wav = voice_service.synthesize_speech("When is the next Amrit Snan?")
        reply = self._send(file=upload("q.wav", wav, "audio/wav"))
        self.assertEqual(reply["metadata"]["route"], "events")
        self.assertEqual(reply["metadata"]["status"], "ok")
        self.assertIn("Live Test Amrit Snan", reply["content"])

    def test_image_question(self):
        image = Image.new("RGB", (200, 120), (255, 255, 255))
        ImageDraw.Draw(image).text((20, 50), "RAMKUND GHAT", fill=(0, 0, 0))
        buffer = io.BytesIO()
        image.resize((800, 480)).save(buffer, format="PNG")
        reply = self._send(
            message="What text is written in this image?",
            file=upload("sign.png", buffer.getvalue(), "image/png"),
        )
        self.assertEqual(reply["metadata"]["status"], "ok")
        self.assertIn("RAMKUND", reply["content"].upper())

    def test_document_question(self):
        reply = self._send(
            message="According to this document, which gate has the first aid post?",
            file=upload("f.pdf", pdf_bytes(["First aid post is located at Gate 9."]), "application/pdf"),
        )
        self.assertEqual(reply["metadata"]["route"], "document")
        self.assertIn("9", reply["content"])
