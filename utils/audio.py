import os
import shutil
import subprocess

# Linux/Docker: ffmpeg is on PATH (installed in the Dockerfile).
# Windows dev machine: set FFMPEG_PATH=C:\ffmpeg\bin\ffmpeg.exe in envs/.env.local
FFMPEG_PATH = os.getenv("FFMPEG_PATH") or shutil.which("ffmpeg") or "ffmpeg"


def convert_audio_to_mp3(input_path: str) -> str:
    """
    Converts audio file to MP3 (speech optimized: mono, 16 kHz, 64 kbps).
    Returns path to converted MP3.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input audio file not found: {input_path}")

    output_path = os.path.splitext(input_path)[0] + ".mp3"
    if os.path.abspath(output_path) == os.path.abspath(input_path):
        output_path = os.path.splitext(input_path)[0] + ".converted.mp3"

    command = [
        FFMPEG_PATH, "-y",
        "-i", input_path,
        "-ac", "1",
        "-ar", "16000",
        "-ab", "64k",
        output_path,
    ]

    try:
        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
            timeout=60,
        )
    except FileNotFoundError:
        raise FileNotFoundError(f"ffmpeg not found (FFMPEG_PATH={FFMPEG_PATH})")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed: {e.stderr.decode(errors='ignore')[-500:]}")

    return output_path