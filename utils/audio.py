import subprocess
import os

# Absolute path to ffmpeg.exe (VERY IMPORTANT on Windows)
FFMPEG_PATH = r"C:\ffmpeg\bin\ffmpeg.exe"

def convert_audio_to_mp3(input_path: str) -> str:
    """
    Converts audio file to MP3 (speech optimized).
    Returns path to converted MP3.
    """

    if not os.path.exists(FFMPEG_PATH):
        raise FileNotFoundError(f"FFmpeg not found at {FFMPEG_PATH}")

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input audio file not found: {input_path}")

    output_path = os.path.splitext(input_path)[0] + ".mp3"

    command = [
        FFMPEG_PATH,
        "-y",
        "-i", input_path,
        "-ac", "1",
        "-ar", "16000",
        "-ab", "64k",
        output_path,
    ]

    subprocess.run(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )

    return output_path
