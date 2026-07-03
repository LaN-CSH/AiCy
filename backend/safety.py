"""안전필터 + 출력 정제 — 기획서 2번/6번.

본격적인 욕설·위험 발언 필터는 4단계(운영 고도화)에서 강화한다.
지금은 (1) 파이프라인에 훅을 마련해두고, (2) TTS로 읽기 좋게 출력만 정제한다.
"""

from __future__ import annotations

import re

# 소리 내어 읽을 때 거슬리는 마크다운/특수문자 제거용.
_STRIP_CHARS = re.compile(r"[*#`_>~]")


def check_input(text: str) -> tuple[bool, str]:
    """입력 통과 여부. 지금은 통과(passthrough). TODO(4단계): 차단 규칙."""
    return True, text.strip()


def clean_output(text: str) -> str:
    """LLM 출력에서 마크다운 흔적 제거 — TTS 발음 품질 보호."""
    text = _STRIP_CHARS.sub("", text)
    # 여러 줄/공백 정리
    text = re.sub(r"\s+\n", "\n", text)
    return text.strip()
