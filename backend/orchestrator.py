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
import re
import sys

import websockets

from backend import persona, safety, tts
from backend.brain import Brain
from backend.chat_source import run_youtube_chat
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
    """프론트 연결 1개를 관리.

    수신 프로토콜(프론트 → 백엔드, JSON 텍스트 프레임):
        {"type": "chat",  "text": "..."}  → 파이프라인 실행(콘솔 입력과 동일 경로)
        {"type": "reset"}                 → 대화기록 초기화
    """
    _clients.add(ws)
    print(f"[ws] 프론트 연결됨 (총 {len(_clients)})")
    # 접속 즉시 백엔드 구성 통지 → 프론트 상태바에 표시
    await ws.send(json.dumps({
        "type": "config",
        "tts": config.TTS_BACKEND,
        "lang": config.LANG,
        "llm": config.LLM_MODEL,
    }))
    try:
        async for raw in ws:
            if isinstance(raw, bytes):
                continue
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if msg.get("type") == "chat":
                text = (msg.get("text") or "").strip()
                if not text:
                    continue
                print(f"[chat] {text}")
                try:
                    await pipeline(text)
                except Exception as exc:  # noqa: BLE001
                    print(f"[pipeline] 오류: {exc}")
            elif msg.get("type") == "reset":
                if _brain is not None:
                    _brain.reset()
                print("[brain] 대화기록 초기화됨")
    finally:
        _clients.discard(ws)
        print(f"[ws] 프론트 연결 해제 (총 {len(_clients)})")


async def _broadcast_json(payload: dict) -> None:
    """오디오 없는 제어/알림 이벤트 브로드캐스트."""
    meta = json.dumps(payload)
    dead = set()
    for ws in _clients:
        try:
            await ws.send(meta)
        except Exception as exc:  # noqa: BLE001
            print(f"[ws] 전송 실패, 연결 제거: {exc}")
            dead.add(ws)
    _clients.difference_update(dead)


async def _broadcast_speak(
    text: str,
    audio: bytes,
    emotion: str = "neutral",
    seq: int = 0,
    last: bool = True,
    full: str = None,
    source: str = "local",
) -> None:
    """speak 이벤트 1개(문장 1개) 전송. full 은 첫 조각에만 실리는 전체 답변.

    source: "local"(콘솔/브라우저 직접 채팅) | "youtube"(방송 채팅에 대한 답변)
    """
    if not _clients:
        print("[ws] 연결된 프론트 없음 — http://localhost:8080/frontend/ 를 열어주세요.")
        return
    payload = {"type": "speak", "text": text, "emotion": emotion,
               "seq": seq, "last": last, "source": source}
    if full is not None:
        payload["full"] = full
    meta = json.dumps(payload)
    dead = set()
    for ws in _clients:
        try:
            await ws.send(meta)
            await ws.send(audio)
        except Exception as exc:  # noqa: BLE001
            print(f"[ws] 전송 실패, 연결 제거: {exc}")
            dead.add(ws)
    _clients.difference_update(dead)


def _split_sentences(text: str):
    """답변을 문장 단위로 분할. 너무 짧은 조각("오!")은 이웃 문장에 병합."""
    parts = re.split(r"(?<=[.!?…])\s+", text.strip())
    parts = [p.strip() for p in parts if p.strip()]
    merged = []
    for p in parts:
        if merged and (len(p) < 6 or len(merged[-1]) < 6):
            merged[-1] += " " + p
        else:
            merged.append(p)
    return merged or [text]


def _should_split() -> bool:
    """느린(RTF>1) 백엔드에서만 자동으로 문장 분할을 켠다."""
    v = config.TTS_SPLIT.lower()
    if v == "auto":
        return config.TTS_BACKEND == "chatterbox"
    return v not in ("0", "false", "no")


async def pipeline(user_text: str, source: str = "local") -> None:
    """한 번의 입력을 답변+음성까지 처리해 프론트로 보낸다.

    문장 분할이 켜져 있으면 문장별로 [합성→전송]을 반복 —
    프론트는 오디오 큐로 끊김 없이 이어 재생하고,
    체감 지연은 '전체 생성'이 아니라 '첫 문장 생성' 시간이 된다.
    """
    ok, user_text = safety.check_input(user_text)
    if not ok:
        print("[safety] 입력 차단됨")
        return

    text = await _to_thread(_get_brain().respond, user_text)
    emotion, text = persona.extract_emotion(text)  # "[happy] ..." → 표정 이벤트
    text = safety.clean_output(text)
    print(f"AiCy> [{emotion}] {text}")

    sentences = _split_sentences(text) if _should_split() else [text]
    for i, sentence in enumerate(sentences):
        audio = await _to_thread(tts.synthesize, sentence)
        await _broadcast_speak(
            sentence, audio, emotion,
            seq=i, last=(i == len(sentences) - 1),
            full=text if i == 0 else None,
            source=source,
        )


async def on_youtube_chat(author: str, text: str) -> None:
    """유튜브 채팅 1건: 프론트 라이브 패널에 중계 후 파이프라인 실행."""
    await _broadcast_json({"type": "live_chat", "author": author, "text": text})
    await pipeline(f"{author}: {text}", source="youtube")


_yt_task = None


def _start_youtube(video_id: str) -> None:
    """YouTube 채팅 감시 태스크 시작(기존 것이 있으면 교체)."""
    global _yt_task
    if _yt_task and not _yt_task.done():
        _yt_task.cancel()
        print("[yt] 기존 감시 중단")
    _yt_task = asyncio.get_event_loop().create_task(
        run_youtube_chat(video_id, on_youtube_chat)
    )


async def _console_loop() -> None:
    """콘솔 입력: 직접 대화 + 제어 명령."""
    print(
        "\n입력 준비 완료. 메시지를 입력하세요."
        "\n(명령: /yt <videoId> 유튜브 채팅 연동, /yt off 중단, "
        "/reset 대화 초기화, /quit 종료)\n"
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
        if line.startswith("/yt"):
            arg = line[3:].strip()
            if arg == "off":
                if _yt_task and not _yt_task.done():
                    _yt_task.cancel()
                    print("[yt] 감시 중단됨")
                else:
                    print("[yt] 실행 중인 감시 없음")
            elif arg:
                _start_youtube(arg)
            else:
                print("사용법: /yt <videoId>  또는  /yt off")
            continue
        try:
            await pipeline(line)
        except Exception as exc:  # noqa: BLE001
            print(f"[pipeline] 오류: {exc}")


def _preflight() -> None:
    """시작 전 환경 점검 — 조용한 런타임 실패 대신 켤 때 크게 실패시킨다."""
    if config.TTS_BACKEND.startswith("chatterbox"):
        try:
            import chatterbox  # noqa: F401
        except ImportError:
            raise SystemExit(
                "\n[오류] TTS가 chatterbox 인데 이 파이썬에는 chatterbox 가 없습니다.\n"
                "       반드시 다음으로 실행하세요:\n"
                "       .venv311\\Scripts\\python -m backend\n"
            )


async def main() -> None:
    _preflight()
    async with websockets.serve(_handler, config.WS_HOST, config.WS_PORT):
        print(f"WebSocket 서버 시작: ws://{config.WS_HOST}:{config.WS_PORT}")
        print(f"LLM={config.LLM_MODEL}  TTS={config.TTS_BACKEND}  LANG={config.LANG}")
        if config.YT_VIDEO_ID:
            _start_youtube(config.YT_VIDEO_ID)
        await _console_loop()
    print("종료합니다.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n종료합니다.")
