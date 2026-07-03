"""Orchestrator — 기획서 5번 아키텍처의 백엔드 본체 (Stage 1 MVP).

파이프라인:
    콘솔 입력(ChatSource) → Brain(LLM) → 안전필터/정제 → TTS → WebSocket push
프론트(아바타)는 WebSocket으로 받은 오디오를 재생하며 립싱크한다.

메시지 프로토콜 (백엔드 → 프론트):
    1) 텍스트 프레임(JSON): {"type": "speak", "text": "...", "emotion": "neutral"}
    2) 바이너리 프레임      : mp3 오디오 바이트 (위 JSON 직후 전송, 순서 보장)

콘솔 입력은 1단계용 임시 ChatSource다. 2단계에서 같은 pipeline()에
YouTube/Chzzk 입력을 끼우면 된다(기획서 3번 'ChatSource 인터페이스').
"""

import asyncio
import json
import sys

import websockets

from backend import safety, tts
from backend.brain import Brain
from backend.config import config

_clients: set = set()
_brain = None  # 지연 초기화: OpenAI 키는 첫 메시지 처리 때만 필요(서버 부팅엔 불필요)


def _get_brain() -> Brain:
    global _brain
    if _brain is None:
        _brain = Brain()
    return _brain


async def _to_thread(fn, *args):
    """블로킹 함수를 스레드에서 실행. asyncio.to_thread는 3.9+이라 3.8 호환용."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fn, *args)


async def _handler(ws) -> None:
    """프론트 연결 1개를 관리. 프론트가 보내는 메시지는 현재 무시(향후 제어용)."""
    _clients.add(ws)
    print(f"[ws] 프론트 연결됨 (총 {len(_clients)})")
    try:
        async for _ in ws:
            pass
    finally:
        _clients.discard(ws)
        print(f"[ws] 프론트 연결 해제 (총 {len(_clients)})")


async def _broadcast_speak(text: str, audio: bytes, emotion: str = "neutral") -> None:
    if not _clients:
        print("[ws] 연결된 프론트 없음 — http://localhost:8080/frontend/ 를 열어주세요.")
        return
    meta = json.dumps({"type": "speak", "text": text, "emotion": emotion})
    dead = set()
    for ws in _clients:
        try:
            await ws.send(meta)
            await ws.send(audio)
        except Exception as exc:  # noqa: BLE001
            print(f"[ws] 전송 실패, 연결 제거: {exc}")
            dead.add(ws)
    _clients.difference_update(dead)


async def pipeline(user_text: str) -> None:
    """한 번의 입력을 답변+음성까지 처리해 프론트로 보낸다."""
    ok, user_text = safety.check_input(user_text)
    if not ok:
        print("[safety] 입력 차단됨")
        return

    text = await _to_thread(_get_brain().respond, user_text)
    text = safety.clean_output(text)
    print(f"AiCy> {text}")

    audio = await _to_thread(tts.synthesize, text)
    await _broadcast_speak(text, audio)


async def _console_loop() -> None:
    """임시 ChatSource: 표준입력에서 한 줄씩 읽어 파이프라인에 넣는다."""
    print(
        "\n입력 준비 완료. 메시지를 입력하세요. "
        "(명령: /reset 대화 초기화, /quit 종료)\n"
    )
    while True:
        line = await _to_thread(sys.stdin.readline)
        if not line:  # EOF
            break
        line = line.strip()
        if not line:
            continue
        if line == "/quit":
            break
        if line == "/reset":
            if _brain is not None:
                _brain.reset()
            print("[brain] 대화기록 초기화됨")
            continue
        try:
            await pipeline(line)
        except Exception as exc:  # noqa: BLE001
            print(f"[pipeline] 오류: {exc}")


async def main() -> None:
    async with websockets.serve(_handler, config.WS_HOST, config.WS_PORT):
        print(f"WebSocket 서버 시작: ws://{config.WS_HOST}:{config.WS_PORT}")
        print(f"LLM={config.LLM_MODEL}  TTS={config.TTS_BACKEND}  LANG={config.LANG}")
        await _console_loop()
    print("종료합니다.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n종료합니다.")
