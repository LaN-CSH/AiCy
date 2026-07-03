"""Chatterbox Turbo 실측 — [laugh] 등 비언어 태그 + 여성 참조 클로닝 + RTF."""

import time

import torch
import torchaudio

from chatterbox.tts_turbo import ChatterboxTurboTTS

DEV = "cuda" if torch.cuda.is_available() else "cpu"
print("device:", DEV)

t0 = time.time()
m = ChatterboxTurboTTS.from_pretrained(device=DEV)
print(f"load: {time.time() - t0:.1f}s")

REF = "audio/aicy-voice-ref.wav"

CASES = {
    "turbo-laugh": ("Okay wait, that is actually hilarious [laugh] "
                    "I can't believe you just said that in chat."),
    "turbo-tags2": ("Honestly [sigh] being an AI is exhausting sometimes. "
                    "[chuckle] Just kidding, I literally never get tired."),
}

for name, text in CASES.items():
    t0 = time.time()
    wav = m.generate(text, audio_prompt_path=REF)
    gen = time.time() - t0
    dur = wav.shape[-1] / m.sr
    torchaudio.save(f"audio/chatterbox-{name}.wav", wav.cpu(), m.sr)
    print(f"[{name}] gen {gen:.1f}s / audio {dur:.1f}s -> RTF {gen / dur:.2f}")

if DEV == "cuda":
    print(f"VRAM peak: {torch.cuda.max_memory_allocated() / 1e9:.2f} GB")
print("saved:", ", ".join(f"chatterbox-{n}.wav" for n in CASES))
