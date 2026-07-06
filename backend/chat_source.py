"""ChatSource — 채팅 입력원 추상화 (기획서 3번 '교체 가능한 부품').

현재 구현: YouTubeChatSource (YouTube Data API v3, API 키만으로 읽기 전용 폴링).
이후 Chzzk 구현체를 같은 인터페이스로 끼우면 플랫폼 전환 완료.

동작 방식:
  1) videos.list(id)            → 그 방송의 activeLiveChatId 획득
  2) liveChatMessages.list 폴링 → 새 메시지 수집 (API 가 권고 간격을 내려줌)
  - 시작 시점 이전의 백로그는 버린다 (과거 채팅에 뒤늦게 답하지 않도록).
  - 파이프라인이 말하는 중에 쌓인 채팅은 '최신 1개'만 남기고 버린다
    (느린 TTS 로 인한 답변 밀림 방지 — 방송에선 최신 흐름을 따라가는 게 자연스러움).

쿼터 참고: liveChatMessages.list 는 호출당 ~5 유닛, 일일 10,000 유닛.
  5초 간격 폴링 ≈ 시간당 3,600 유닛 → 테스트/단시간 방송용. 장시간 무인 방송은
  4단계에서 간격 조정 또는 대체 수집기 검토.
"""

import asyncio

import requests

from backend.config import config

_API = "https://www.googleapis.com/youtube/v3"


class YouTubeChatSource:
    def __init__(self, video_id: str):
        if not config.YOUTUBE_API_KEY:
            raise RuntimeError("YOUTUBE_API_KEY 가 .env 에 없습니다.")
        self.video_id = video_id
        self.chat_id = None
        self._page_token = None
        self._started = False  # 첫 폴링(백로그 스킵) 완료 여부

    # --- blocking HTTP (스레드에서 호출) ---

    def _get(self, path: str, **params) -> dict:
        params["key"] = config.YOUTUBE_API_KEY
        r = requests.get(f"{_API}/{path}", params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    def resolve_chat_id(self) -> str:
        data = self._get(
            "videos", part="liveStreamingDetails,snippet", id=self.video_id
        )
        items = data.get("items") or []
        if not items:
            raise RuntimeError(f"영상 없음: {self.video_id}")
        details = items[0].get("liveStreamingDetails") or {}
        chat_id = details.get("activeLiveChatId")
        if not chat_id:
            raise RuntimeError(
                "activeLiveChatId 없음 — 방송이 라이브 상태인지, "
                "채팅이 켜져 있는지(어린이용 아님) 확인하세요."
            )
        self.chat_id = chat_id
        title = items[0].get("snippet", {}).get("title", "?")
        print(f"[yt] 라이브 연결됨: \"{title}\" (chat id 확보)")
        return chat_id

    def poll(self) -> tuple:
        """(새 메시지 리스트[(author, text)], 다음 폴링까지 대기 초)"""
        params = {
            "liveChatId": self.chat_id,
            "part": "snippet,authorDetails",
            "maxResults": 200,
        }
        if self._page_token:
            params["pageToken"] = self._page_token
        data = self._get("liveChat/messages", **params)
        self._page_token = data.get("nextPageToken")
        wait = max(data.get("pollingIntervalMillis", 5000) / 1000.0,
                   config.YT_POLL_MIN)

        messages = []
        for item in data.get("items", []):
            snip = item.get("snippet", {})
            if snip.get("type") != "textMessageEvent":
                continue  # 슈퍼챗/멤버십 등은 4단계에서
            text = (snip.get("displayMessage") or "").strip()
            author = item.get("authorDetails", {}).get("displayName", "?")
            if text:
                messages.append((author, text))

        if not self._started:
            # 첫 폴링 결과 = 접속 이전의 백로그 → 버림
            self._started = True
            if messages:
                print(f"[yt] 이전 채팅 {len(messages)}개 스킵 (백로그)")
            return [], wait
        return messages, wait


async def run_youtube_chat(video_id: str, handler) -> None:
    """YouTube 채팅 폴링 루프. 새 채팅을 handler(author, text) 코루틴에 넣는다."""
    src = YouTubeChatSource(video_id)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, src.resolve_chat_id)
    print("[yt] 채팅 감시 시작 — 방송 채팅창에 말을 걸어보세요.")

    while True:
        try:
            messages, wait = await loop.run_in_executor(None, src.poll)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            if status == 403:
                print(f"[yt] API 쿼터/권한 오류(403) — 60초 후 재시도: {exc}")
                await asyncio.sleep(60)
                continue
            print(f"[yt] HTTP 오류({status}) — 15초 후 재시도")
            await asyncio.sleep(15)
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"[yt] 폴링 오류 — 15초 후 재시도: {exc}")
            await asyncio.sleep(15)
            continue

        if messages:
            # 말하는 동안 쌓인 채팅은 최신 것 하나만 처리 (밀림 방지)
            if len(messages) > 1:
                skipped = ", ".join(a for a, _ in messages[:-1])
                print(f"[yt] {len(messages) - 1}개 스킵({skipped}) — 최신 채팅만 응답")
            author, text = messages[-1]
            print(f"[yt] {author}: {text}")
            try:
                await handler(author, text)
            except Exception as exc:  # noqa: BLE001
                print(f"[yt] handler 오류: {exc}")

        await asyncio.sleep(wait)
