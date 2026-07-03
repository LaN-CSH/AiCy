"""두뇌(LLM) — OpenAI 호출 + 세션 대화기록.

레거시 ai_core/openai.py 의 호출 패턴을 이식하되 페르소나를 AiCy로 통일.
대화기록은 프로세스 메모리에 유지(세션 한정). 영속 기억은 기획서 4단계.
"""

from openai import OpenAI

from backend.config import config
from backend.persona import system_prompt


class Brain:
    def __init__(self) -> None:
        if not config.OPENAI_KEY:
            raise RuntimeError(
                "OPENAI_KEY 가 설정되지 않았습니다. .env 를 확인하세요."
            )
        self.client = OpenAI(api_key=config.OPENAI_KEY)
        self._system = {"role": "system", "content": system_prompt(config.LANG)}
        self.conversation = [self._system]

    def respond(self, user_text: str) -> str:
        """사용자 발화 → AiCy 답변 텍스트. (동기 호출, 스레드에서 await)"""
        self.conversation.append({"role": "user", "content": user_text})
        resp = self.client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=self.conversation,
        )
        text = resp.choices[0].message.content or ""
        self.conversation.append({"role": "assistant", "content": text})
        return text

    def reset(self) -> None:
        self.conversation = [self._system]
