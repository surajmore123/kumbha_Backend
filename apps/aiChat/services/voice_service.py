"""
Optional spoken replies (text-to-speech) with Gemini's TTS model.

This uses the `google-genai` SDK directly because the LangChain chat
wrapper does not return generated audio. It is off unless
`AI_VOICE_REPLY_ENABLED` is true and the client asks for `voice_reply`.
The text answer is always returned; a TTS failure only omits the audio.
"""

import io
import logging
import re
import wave

from apps.aiChat import ai_config

logger = logging.getLogger(__name__)

# Gemini TTS returns 16-bit mono PCM at 24 kHz.
_SAMPLE_RATE = 24000


class VoiceServiceError(Exception):
    pass


def _speakable(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)            # links aren't read out
    text = re.sub(r"[*_#`>|\[\]]", "", text)            # markdown symbols
    text = re.sub(r"\s+", " ", text).strip()
    return text[: ai_config.voice_reply_max_chars()]


def pcm_to_wav(pcm: bytes, sample_rate: int = _SAMPLE_RATE) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def synthesize_speech(text: str, *, timeout: float | None = None) -> bytes:
    """Return WAV bytes for `text`, or raise `VoiceServiceError`."""
    speakable = _speakable(text)
    if not speakable:
        raise VoiceServiceError("Nothing to speak.")
    api_key = ai_config.gemini_api_key()
    if not api_key:
        raise VoiceServiceError("Gemini API key is not configured.")

    try:
        from google import genai
        from google.genai import types

        seconds = ai_config.model_timeout_seconds()
        if timeout is not None:
            seconds = max(1, min(seconds, int(timeout)))
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=seconds * 1000),
        )
        response = client.models.generate_content(
            model=ai_config.tts_model_name(),
            contents=speakable,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=ai_config.tts_voice_name(),
                        )
                    )
                ),
            ),
        )
        pcm = response.candidates[0].content.parts[0].inline_data.data
    except Exception as exc:  # noqa: BLE001 - optional feature, never fatal
        logger.error("Voice reply generation failed (%s).", type(exc).__name__)
        raise VoiceServiceError("Voice generation failed.") from exc

    if not pcm:
        raise VoiceServiceError("Voice generation returned no audio.")
    return pcm_to_wav(pcm)
