"""음성 합성(TTS) — 텍스트 → mp3 bytes.

백엔드 교체 가능(기획서 3번 원칙):
- edge:       MS Edge 뉴럴 음성(클라우드, 무료·키 불필요). 한국어 SunHi 등. 품질 좋음.
- sapi:       Windows 내장 음성(System.Speech). 로컬·오프라인·GPU 불필요. 키 불필요.
- elevenlabs: 클라우드 고품질(키 필요). 레거시 gtts_test.py 의 REST 호출 패턴 이식.
- gtts:       Google TTS(클라우드). 키 없이 쓸 수 있는 폴백.

로컬 뉴럴 TTS(Orpheus·Chatterbox 등)는 여기에 함수 하나 + config 값만 추가하면
끼울 수 있다. 파이프라인 나머지는 출력이 mp3 bytes 이기만 하면 무관.
피치 조정(AICY_VOICE_PITCH)은 어떤 백엔드든 공통 후처리로 적용된다.
"""

import asyncio
import io
import os
import shutil
import subprocess
import tempfile

import requests

from backend.config import config

_BACKENDS = {}


def synthesize(text: str) -> bytes:
    """텍스트를 mp3 바이트로 합성. 백엔드는 config.TTS_BACKEND 로 선택."""
    fn = _BACKENDS.get(config.TTS_BACKEND, _elevenlabs)
    audio = fn(text)
    if config.VOICE_PITCH and abs(config.VOICE_PITCH - 1.0) > 0.01:
        audio = _pitch_shift(audio, config.VOICE_PITCH)
    return audio


def _find_ffmpeg() -> str:
    if config.FFMPEG:
        return config.FFMPEG
    for cand in ("ffmpeg", "C:/ffmpeg/ffmpeg.exe"):
        if shutil.which(cand) or os.path.exists(cand):
            return cand
    raise RuntimeError(
        "ffmpeg 를 찾을 수 없습니다. PATH 에 추가하거나 AICY_FFMPEG 로 경로를 지정하세요."
    )


def _pitch_shift(audio: bytes, pitch: float) -> bytes:
    """피치만 올리고 길이는 유지: 48k 리샘플 → asetrate 피치업 → atempo 속도 보정."""
    ffmpeg = _find_ffmpeg()
    src = tempfile.mktemp(suffix=".mp3")
    dst = tempfile.mktemp(suffix=".mp3")
    try:
        with open(src, "wb") as f:
            f.write(audio)
        af = (f"aresample=48000,asetrate={int(48000 * pitch)},"
              f"aresample=48000,atempo={1 / pitch:.4f}")
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", src,
             "-af", af, "-codec:a", "libmp3lame", "-qscale:a", "4", dst],
            check=True,
            capture_output=True,
        )
        with open(dst, "rb") as f:
            return f.read()
    finally:
        for p in (src, dst):
            try:
                os.remove(p)
            except OSError:
                pass


_cb_model = None


def _tensor_to_mp3(wav, sr: int) -> bytes:
    """오디오 텐서 → mp3 bytes (ffmpeg 경유)."""
    import torchaudio

    ffmpeg = _find_ffmpeg()
    w = tempfile.mktemp(suffix=".wav")
    m = tempfile.mktemp(suffix=".mp3")
    try:
        torchaudio.save(w, wav.cpu(), sr)
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", w,
             "-codec:a", "libmp3lame", "-qscale:a", "4", m],
            check=True,
            capture_output=True,
        )
        with open(m, "rb") as f:
            return f.read()
    finally:
        for p in (w, m):
            try:
                os.remove(p)
            except OSError:
                pass


def _chatterbox(text: str) -> bytes:
    """Chatterbox(로컬 뉴럴 0.5B, MIT) — 첫 호출에 모델을 GPU에 상주시킨다.

    LANG=ko 면 다국어 모델(language_id='ko'), 아니면 영어 전용 모델.
    ⚠️ chatterbox 는 Python 3.11 venv 에만 설치됨 → 백엔드를
       `.venv311\\Scripts\\python -m backend` 로 실행해야 한다.
    디바이스는 cuda → mps(맥) → cpu 자동 선택.
    """
    global _cb_model
    import torch

    if _cb_model is None:
        if torch.cuda.is_available():
            dev = "cuda"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            dev = "mps"
        else:
            dev = "cpu"
        if config.LANG == "ko":
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
            _cb_model = ChatterboxMultilingualTTS.from_pretrained(device=dev)
        else:
            from chatterbox.tts import ChatterboxTTS
            _cb_model = ChatterboxTTS.from_pretrained(device=dev)
        print(f"[tts] chatterbox 모델 상주 완료 ({dev}, lang={config.LANG})")

    kwargs = {"exaggeration": config.CB_EXAGGERATION, "cfg_weight": config.CB_CFG}
    if config.CB_REF_AUDIO:
        kwargs["audio_prompt_path"] = config.CB_REF_AUDIO
    if config.LANG == "ko":
        wav = _cb_model.generate(text, language_id="ko", **kwargs)
    else:
        wav = _cb_model.generate(text, **kwargs)
    return _tensor_to_mp3(wav, _cb_model.sr)


_cb_turbo_model = None


def _chatterbox_turbo(text: str) -> bytes:
    """Chatterbox Turbo — 실시간보다 빠름(4060 Ti 실측 RTF 0.4~0.6) + 비언어 태그.

    텍스트 안에 [laugh] [sigh] [chuckle] 같은 태그를 쓰면 소리로 연기한다.
    ⚠️ 영어 전용. exaggeration/cfg 는 Turbo 에선 무시됨. .venv311 필요.
    """
    global _cb_turbo_model
    import torch

    if _cb_turbo_model is None:
        if torch.cuda.is_available():
            dev = "cuda"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            dev = "mps"
        else:
            dev = "cpu"
        from chatterbox.tts_turbo import ChatterboxTurboTTS
        _cb_turbo_model = ChatterboxTurboTTS.from_pretrained(device=dev)
        print(f"[tts] chatterbox-turbo 모델 상주 완료 ({dev}) — 영어 전용")

    kwargs = {}
    if config.CB_REF_AUDIO:
        kwargs["audio_prompt_path"] = config.CB_REF_AUDIO
    wav = _cb_turbo_model.generate(text, **kwargs)
    return _tensor_to_mp3(wav, _cb_turbo_model.sr)


def _edge(text: str) -> bytes:
    """MS Edge 뉴럴 음성(edge-tts). 클라우드지만 무료·키 불필요. 출력이 원래 mp3."""
    import edge_tts

    voice = config.EDGE_VOICE or (
        "ko-KR-SunHiNeural" if config.LANG == "ko" else "en-US-AriaNeural"
    )

    async def _run() -> bytes:
        buf = bytearray()
        async for chunk in edge_tts.Communicate(text, voice).stream():
            if chunk["type"] == "audio":
                buf.extend(chunk["data"])
        return bytes(buf)

    # synthesize()는 워커 스레드(이벤트 루프 없음)에서 불린다.
    # Windows+Py3.8의 Proactor 종료 소음("Event loop is closed")을 피하려고
    # Selector 루프를 명시적으로 만들어 쓴다.
    loop = asyncio.SelectorEventLoop()
    try:
        return loop.run_until_complete(_run())
    finally:
        loop.close()


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


_BACKENDS.update({
    "chatterbox": _chatterbox,
    "chatterbox_turbo": _chatterbox_turbo,
    "edge": _edge,
    "sapi": _sapi,
    "gtts": _gtts,
    "elevenlabs": _elevenlabs,
})
