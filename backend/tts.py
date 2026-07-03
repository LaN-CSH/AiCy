"""음성 합성(TTS) — 텍스트 → mp3 bytes.

백엔드 교체 가능(기획서 3번 원칙):
- sapi:       Windows 내장 음성(System.Speech). 로컬·오프라인·GPU 불필요. 키 불필요.
- elevenlabs: 기획 기본(클라우드). 레거시 gtts_test.py 의 REST 호출 패턴 이식.
- gtts:       Google TTS(클라우드). 키 없이 쓸 수 있는 폴백.

로컬 경량/자연 TTS(Piper·Kokoro 등)는 여기에 `_piper()` 등 함수 하나 + config 값만
추가하면 끼울 수 있다. 파이프라인 나머지는 출력이 mp3 bytes 이기만 하면 무관.
"""

import io
import os
import shutil
import subprocess
import tempfile

import requests

from backend.config import config


def synthesize(text: str) -> bytes:
    """텍스트를 mp3 바이트로 합성. 백엔드는 config.TTS_BACKEND 로 선택."""
    if config.TTS_BACKEND == "sapi":
        return _sapi(text)
    if config.TTS_BACKEND == "gtts":
        return _gtts(text)
    return _elevenlabs(text)


def _find_ffmpeg() -> str:
    if config.FFMPEG:
        return config.FFMPEG
    for cand in ("ffmpeg", "C:/ffmpeg/ffmpeg.exe"):
        if shutil.which(cand) or os.path.exists(cand):
            return cand
    raise RuntimeError(
        "ffmpeg 를 찾을 수 없습니다. PATH 에 추가하거나 AICY_FFMPEG 로 경로를 지정하세요."
    )


def _sapi(text: str) -> bytes:
    """Windows SAPI(System.Speech)로 로컬 합성 → WAV → mp3 변환.

    텍스트는 한글 인코딩 안전을 위해 UTF-8 임시파일로 넘긴다(PowerShell이 읽음).
    """
    voice = config.SAPI_VOICE or (
        "Microsoft Heami Desktop" if config.LANG == "ko" else "Microsoft Zira Desktop"
    )
    ffmpeg = _find_ffmpeg()
    txt = tempfile.mktemp(suffix=".txt")
    wav = tempfile.mktemp(suffix=".wav")
    mp3 = tempfile.mktemp(suffix=".mp3")
    try:
        with open(txt, "w", encoding="utf-8") as f:
            f.write(text)
        ps = (
            "Add-Type -AssemblyName System.Speech;"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            f'$s.SelectVoice("{voice}");'
            f'$s.SetOutputToWaveFile("{wav}");'
            f'$t = Get-Content -Raw -Encoding UTF8 "{txt}";'
            "$s.Speak($t); $s.Dispose()"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", wav,
             "-codec:a", "libmp3lame", "-qscale:a", "4", mp3],
            check=True,
            capture_output=True,
        )
        with open(mp3, "rb") as f:
            return f.read()
    finally:
        for p in (txt, wav, mp3):
            try:
                os.remove(p)
            except OSError:
                pass


def _elevenlabs(text: str) -> bytes:
    if not config.ELEVENLABS_KEY:
        raise RuntimeError(
            "ELEVENLABS 키가 없습니다. .env 에 키를 넣거나 "
            "AICY_TTS_BACKEND=gtts 로 무료 폴백을 쓰세요."
        )
    url = (
        "https://api.elevenlabs.io/v1/text-to-speech/"
        + config.ELEVENLABS_VOICE_ID
    )
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": config.ELEVENLABS_KEY,
    }
    data = {
        "text": text,
        "model_id": config.ELEVENLABS_MODEL,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.3},
    }
    resp = requests.post(url, json=data, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.content


def _gtts(text: str) -> bytes:
    from gtts import gTTS

    buf = io.BytesIO()
    gTTS(text=text, lang=config.tts_lang(), slow=False).write_to_fp(buf)
    return buf.getvalue()
