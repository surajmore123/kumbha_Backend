import base64
import io
import os
import unittest
from unittest import mock

from PIL import Image

from apps.aiChat.attachments import audio as audio_module
from apps.aiChat.attachments.errors import AttachmentError
from apps.aiChat.models import ChatMessage
from apps.aiChat.services.gemini_service import GeminiServiceError
from apps.aiChat.services.transcription_service import Transcript
from apps.aiChat.services.voice_service import VoiceServiceError
from apps.aiChat.tests.helpers import (
    GuruTestCase,
    jpeg_with_exif,
    make_event,
    make_temple,
    png_bytes,
    upload,
    wav_bytes,
)


def _blocks(model, kind):
    return [b for b in model.call_args.args[0] if b.get("type") == kind]


class ImageTests(GuruTestCase):
    def test_image_with_question_sends_real_image_bytes(self):
        model = self.mock_model("A saffron flag is visible.")
        data = png_bytes()
        reply = self.reply(self.send("What is shown in this image?", upload("photo.png", data, "image/png")))

        [image] = _blocks(model, "image")
        self.assertEqual(image["mime_type"], "image/png")
        self.assertEqual(base64.b64decode(image["base64"]), data)
        self.assertEqual(reply["metadata"]["route"], "image")
        user_message = self.messages()[0]
        self.assertEqual(user_message.message_type, "image")
        self.assertEqual(user_message.metadata["content_type"], "image/png")
        self.assertTrue(user_message.file_url)
        self.assertIn("separate what is visibly present", self.system_prompt(model))

    def test_image_without_text_gets_default_prompt(self):
        model = self.mock_model("It shows a river ghat.")
        self.reply(self.send(file=upload("ghat.png", png_bytes(), "image/png")))
        self.assertIn("Describe what is shown in this image", self.prompt_text(model))

    def test_image_with_temple_question_also_gets_temple_data(self):
        model = self.mock_model("This may be Trimbakeshwar.")
        make_temple()
        reply = self.reply(self.send(
            "Is this the Trimbakeshwar temple?", upload("t.png", png_bytes(), "image/png"),
        ))
        self.assertEqual(reply["metadata"]["intents"][:2], ["image", "temple"])
        self.assertIn("Trimbakeshwar Jyotirling Mandir", self.prompt_text(model))

    def test_exif_metadata_is_removed_before_storage_and_model(self):
        model = self.mock_model("ok")
        self.reply(self.send("what is this", upload("p.jpg", jpeg_with_exif(), "image/jpeg")))
        [image] = _blocks(model, "image")
        sent = Image.open(io.BytesIO(base64.b64decode(image["base64"])))
        self.assertFalse(sent.getexif())

    def test_mismatched_content_is_rejected_and_not_stored(self):
        model = self.mock_model()
        reply = self.reply(self.send(
            "what is this", upload("photo.png", b"%PDF-1.4 not an image", "image/png"),
        ))
        self.assertEqual(reply["metadata"]["error"], "type_mismatch")
        self.assertIsNone(self.messages()[0].file_url)
        model.assert_not_called()
        self.assertFalse(os.listdir(self.media))

    def test_unsupported_binary_is_rejected(self):
        self.mock_model()
        reply = self.reply(self.send(file=upload("x.bin", b"\x00\x01\x02garbage", "application/octet-stream")))
        self.assertEqual(reply["metadata"]["error"], "unsupported_file")

    def test_corrupt_image_is_rejected(self):
        self.mock_model()
        broken = png_bytes()[:40] + b"\x00" * 20
        reply = self.reply(self.send(file=upload("b.png", broken, "image/png")))
        self.assertEqual(reply["metadata"]["error"], "corrupt_image")
        self.assertIn("could not be opened", reply["content"])

    def test_oversized_image_is_rejected(self):
        self.mock_model()
        with mock.patch.dict(os.environ, {"AI_MAX_IMAGE_MB": "1"}):
            big = png_bytes() + b"\x00" * (1024 * 1024 + 10)
            reply = self.reply(self.send(file=upload("big.png", big, "image/png")))
        self.assertEqual(reply["metadata"]["error"], "file_too_large")
        self.assertIn("1 MB", reply["content"])

    def test_upload_above_hard_cap_is_a_400(self):
        with mock.patch.dict(os.environ, {
            "AI_MAX_IMAGE_MB": "1", "AI_MAX_AUDIO_MB": "1", "AI_MAX_DOCUMENT_MB": "1",
        }):
            response = self.send(file=upload("huge.png", b"\x89PNG" + b"\x00" * (2 * 1024 * 1024), "image/png"))
        self.assertEqual(response.status_code, 400)

    def test_heic_is_reported_as_unsupported(self):
        self.mock_model()
        heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64
        reply = self.reply(self.send(file=upload("p.heic", heic, "image/heic")))
        self.assertEqual(reply["metadata"]["error"], "unsupported_image")

    def test_model_failure_on_image_says_it_was_not_analysed(self):
        self.mock_model(side_effect=GeminiServiceError("down"))
        reply = self.reply(self.send("what is this?", upload("p.png", png_bytes(), "image/png")))
        self.assertEqual(reply["metadata"]["status"], "error")
        self.assertIn("couldn't analyse this image", reply["content"])

    def test_follow_up_about_previous_photo_reattaches_it(self):
        self.mock_model("A temple.")
        data = png_bytes(color=(1, 2, 3))
        self.send("what is this", upload("p.png", data, "image/png"))
        model = self.mock_model("The sign says Ramkund.")
        self.send("What does the sign in the photo say?")
        [image] = _blocks(model, "image")
        self.assertEqual(base64.b64decode(image["base64"]), data)


class AudioTests(GuruTestCase):
    def mock_transcript(self, text="When is the next Amrit Snan?", speech=True, language="en", error=None):
        patcher = mock.patch(
            "apps.aiChat.graph.transcribe_audio",
            return_value=Transcript(speech, language, text),
            side_effect=error,
        )
        transcriber = patcher.start()
        self.addCleanup(patcher.stop)
        return transcriber

    def test_spoken_question_is_answered_with_the_same_tools(self):
        transcriber = self.mock_transcript()
        model = self.mock_model("The next Amrit Snan is ...")
        make_event("Amrit Snan One")
        data = wav_bytes()
        reply = self.reply(self.send(file=upload("voice.wav", data, "audio/wav")))

        sent_bytes, sent_type = transcriber.call_args.args
        self.assertEqual(sent_bytes, data)
        self.assertEqual(sent_type, "audio/wav")
        self.assertEqual(reply["metadata"]["route"], "events")
        self.assertEqual(reply["metadata"]["transcript"]["text"], "When is the next Amrit Snan?")
        self.assertIn("Amrit Snan One", self.prompt_text(model))
        self.assertIn("spoken in a voice message", self.prompt_text(model))
        user_message = self.messages()[0]
        self.assertEqual(user_message.message_type, "audio")
        self.assertEqual(user_message.metadata["transcript"]["text"], "When is the next Amrit Snan?")
        self.assertEqual(user_message.metadata["attachment"]["duration_seconds"], 1.0)

    def test_hindi_speech_sets_reply_language(self):
        self.mock_transcript("अगला शाही स्नान कब है?", language="hi")
        self.mock_model()
        reply = self.reply(self.send(file=upload("v.wav", wav_bytes(), "audio/wav")))
        self.assertEqual(reply["metadata"]["language"], "hi")
        self.assertIn("कोई आगामी", reply["content"])

    def test_silent_recording_is_detected_without_model_calls(self):
        transcriber = self.mock_transcript()
        model = self.mock_model()
        reply = self.reply(self.send(file=upload("s.wav", wav_bytes(amplitude=0), "audio/wav")))
        self.assertEqual(reply["metadata"]["error"], "silent_audio")
        self.assertIn("couldn't hear any speech", reply["content"])
        transcriber.assert_not_called()
        model.assert_not_called()

    def test_no_speech_reported_by_model(self):
        self.mock_transcript(text="", speech=False)
        model = self.mock_model()
        reply = self.reply(self.send(file=upload("n.wav", wav_bytes(), "audio/wav")))
        self.assertIn("couldn't hear any speech", reply["content"])
        model.assert_not_called()

    def test_no_speech_with_typed_question_uses_direct_audio_understanding(self):
        self.mock_transcript(text="", speech=False)
        model = self.mock_model("It sounds like a conch shell.")
        self.reply(self.send("What sound is this?", upload("c.wav", wav_bytes(), "audio/wav")))
        self.assertEqual(len(_blocks(model, "audio")), 1)

    def test_empty_recording(self):
        self.mock_model()
        reply = self.reply(self.send(file=upload("e.wav", wav_bytes(seconds=0), "audio/wav")))
        self.assertEqual(reply["metadata"]["error"], "empty_audio")

    def test_too_long_recording(self):
        self.mock_model()
        with mock.patch.dict(os.environ, {"AI_MAX_AUDIO_SECONDS": "1"}):
            reply = self.reply(self.send(file=upload("l.wav", wav_bytes(seconds=2), "audio/wav")))
        self.assertEqual(reply["metadata"]["error"], "audio_too_long")

    def test_corrupt_audio_reported_by_decoder(self):
        self.mock_model()
        with mock.patch.object(
            audio_module, "_probe_duration", side_effect=AttachmentError("corrupt_audio"),
        ):
            reply = self.reply(self.send(file=upload("c.mp3", b"ID3" + b"\x00" * 200, "audio/mpeg")))
        self.assertEqual(reply["metadata"]["error"], "corrupt_audio")

    def test_m4a_without_ffmpeg_is_rejected_clearly(self):
        self.mock_model()
        m4a = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 200
        with mock.patch.object(audio_module, "ffmpeg_path", return_value=None):
            reply = self.reply(self.send(file=upload("r.m4a", m4a, "audio/mp4")))
        self.assertEqual(reply["metadata"]["error"], "audio_conversion_unavailable")

    def test_transcription_failure(self):
        self.mock_transcript(error=GeminiServiceError("down"))
        model = self.mock_model()
        reply = self.reply(self.send(file=upload("v.wav", wav_bytes(), "audio/wav")))
        self.assertIn("couldn't process this voice message", reply["content"])
        model.assert_not_called()

    def test_voice_reply_failure_keeps_text_answer(self):
        self.mock_model("Namaste.")
        with mock.patch.dict(os.environ, {"AI_VOICE_REPLY_ENABLED": "true"}), mock.patch(
            "apps.aiChat.services.chat_orchestrator.synthesize_speech",
            side_effect=VoiceServiceError("tts down"),
        ):
            reply = self.reply(self.send("Hello", voice_reply=True))
        self.assertEqual(reply["content"], "Namaste.")
        self.assertEqual(reply["metadata"]["voice"], {"status": "failed"})

    def test_voice_reply_success_returns_playable_url(self):
        self.mock_model("Namaste.")
        with mock.patch.dict(os.environ, {"AI_VOICE_REPLY_ENABLED": "true"}), mock.patch(
            "apps.aiChat.services.chat_orchestrator.synthesize_speech",
            return_value=wav_bytes(),
        ):
            reply = self.reply(self.send("Hello", voice_reply=True))
        voice = reply["metadata"]["voice"]
        self.assertEqual(voice["status"], "ok")
        self.assertTrue(voice["url"].endswith(".wav"))
        self.assertIn("/voice/", voice["url"])

    def test_voice_reply_disabled_by_default(self):
        self.mock_model("Namaste.")
        reply = self.reply(self.send("Hello", voice_reply=True))
        self.assertEqual(reply["metadata"]["voice"], {"status": "disabled"})

    @unittest.skipUnless(audio_module.ffmpeg_path(), "ffmpeg is not installed")
    def test_m4a_is_converted_with_ffmpeg(self):
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "in.wav")
            target = os.path.join(folder, "out.m4a")
            with open(source, "wb") as handle:
                handle.write(wav_bytes(seconds=1))
            subprocess.run(
                [audio_module.ffmpeg_path(), "-y", "-loglevel", "error", "-i", source,
                 "-c:a", "aac", target],
                check=True, timeout=60,
            )
            with open(target, "rb") as handle:
                m4a = handle.read()
        transcriber = self.mock_transcript()
        self.mock_model("ok")
        make_event()
        self.reply(self.send(file=upload("r.m4a", m4a, "audio/mp4")))
        self.assertEqual(transcriber.call_args.args[1], "audio/mp3")
        self.assertTrue(ChatMessage.objects.get(role="user").metadata["attachment"]["converted"])
