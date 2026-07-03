"""Chatterbox 첫 실측 — 영어(기본 모델) + 한국어(다국어 모델).
로드 시간 / 생성 시간 / RTF(실시간 배율) / VRAM 측정. 결과 wav 저장."""

import time

import torch
import torchaudio


def pick_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


DEV = pick_device()
print("device:", DEV, "|", torch.cuda.get_device_name(0) if DEV == "cuda" else "")

# ---------- 영어 (본토 품질) ----------
from chatterbox.tts import ChatterboxTTS

t0 = time.time()
en = ChatterboxTTS.from_pretrained(device=DEV)
print(f"[EN] model load: {time.time() - t0:.1f}s")

TEXT_EN = ("Hey everyone, welcome back! I'm AiCy, your favorite AI VTuber. "
           "Today we are testing my brand new voice. So, how do I sound?")

t0 = time.time()
wav = en.generate(TEXT_EN, exaggeration=0.6)
gen = time.time() - t0
dur = wav.shape[-1] / en.sr
torchaudio.save("chatterbox-en.wav", wav.cpu(), en.sr)
print(f"[EN] gen {gen:.1f}s / audio {dur:.1f}s -> RTF {gen / dur:.2f}")

# 워밍업 이후 실측 (첫 호출엔 CUDA 커널 준비 오버헤드가 섞임)
t0 = time.time()
wav2 = en.generate("This is the warmed up second run, checking real speed.")
gen2 = time.time() - t0
dur2 = wav2.shape[-1] / en.sr
print(f"[EN] warm gen {gen2:.1f}s / audio {dur2:.1f}s -> RTF {gen2 / dur2:.2f}")

if DEV == "cuda":
    print(f"[EN] VRAM peak: {torch.cuda.max_memory_allocated() / 1e9:.2f} GB")

del en
if DEV == "cuda":
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

# ---------- 한국어 (다국어 모델) ----------
from chatterbox.mtl_tts import ChatterboxMultilingualTTS

t0 = time.time()
ml = ChatterboxMultilingualTTS.from_pretrained(device=DEV)
print(f"[KO] model load: {time.time() - t0:.1f}s")

TEXT_KO = "안녕! 나는 아이시야. 이건 채터박스 다국어 모델로 만든 한국어 목소리야. 어때, 자연스럽게 들려?"

t0 = time.time()
wav = ml.generate(TEXT_KO, language_id="ko", exaggeration=0.6)
gen = time.time() - t0
dur = wav.shape[-1] / ml.sr
torchaudio.save("chatterbox-ko.wav", wav.cpu(), ml.sr)
print(f"[KO] gen {gen:.1f}s / audio {dur:.1f}s -> RTF {gen / dur:.2f}")

if DEV == "cuda":
    print(f"[KO] VRAM peak: {torch.cuda.max_memory_allocated() / 1e9:.2f} GB")

print("saved: chatterbox-en.wav, chatterbox-ko.wav")
