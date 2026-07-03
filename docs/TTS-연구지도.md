# TTS 미해결 한계 & 연구 지도

> AiCy 프로젝트의 핵심 차별화 = **사람처럼 비언어 표현까지 하는 오디오 모델**.
> 이 문서는 그 목표 기준으로 "지금 최신 TTS가 못 넘은 것"과 "공부할 연구 축"을 정리한 노트.
>
> 작성: 2026-06-17 · 근거: 2025~26 상반기 논문/벤치마크 (하단 Sources)

## 전제 (프로젝트 결정사항)

| 항목 | 결정 |
|---|---|
| 언어 | **영어 우선** (품질 우선, 한국어는 이후 확장 — 기획서 플랫폼 전략과 일치) |
| 인프라 | **학습 = SLURM 서버 / 추론 = 로컬 RTX 4060 8GB** (오디오 모델은 0.5B~3B라 분업 성립) |
| 현 단계 | 캐스케이드 구조 (LLM → 감정태그 → TTS). 풀듀플렉스는 장기 목표 |

---

## 1. 최신 TTS가 아직 못 넘은 한계

**프레임: "문장 하나 잘 읽기"는 사실상 정복됨** (MOS에서 인간 녹음을 넘는 모델 다수).
남은 문제는 전부 **문장 너머**에 있고 — 공교롭게도 전부 버튜버가 필요로 하는 것들이다.

| # | 한계 | 왜 어려운가 |
|---|---|---|
| ① | **대화 문맥 운율 단절** | 거의 모든 TTS가 문장을 독립적으로 합성 → 턴이 바뀌면 감정·톤·음역이 리셋. 10분 대화에서 "같은 사람이 이어 말하는 느낌"이 안 남. CSS(Conversational Speech Synthesis)가 활발하지만 미해결 |
| ② | **"언제·어떻게 말할지" 판단 부재** | 스타일을 태그/프롬프트로 사람이 지정해야 함. 문맥을 읽고 스스로 말투를 정하는 추론은 이제 막 챌린지가 열린 프런티어 (ISCSLP 2026 CoT-TTS) |
| ③ | **비언어 표현의 '통조림' 문제** | `<laugh>` 태그는 되지만 박제된 느낌. 웃음의 길이·횟수·강도 세밀 제어 불가. "웃으면서 말하기"(speech-laugh) 같은 혼합 발성은 거의 안 됨 |
| ④ | **감정 ↔ 화자 정체성 얽힘** | 감정을 바꾸면 목소리 정체성이 미묘하게 흔들림(entanglement). 감정의 연속값·혼합·문장 내 전이 제어 미해결 |
| ⑤ | **풀듀플렉스 상호작용** | 사람은 들으면서 말함(맞장구·끼어들기·말 겹침). 턴 기반 캐스케이드로는 원리적으로 불가. Moshi(160~200ms)가 프런티어지만 지능↔음질 트레이드오프 큼 |
| ⑥ | **AR 환각·안정성** | 토큰 LM 계열은 단어 건너뛰기/반복/유령 소리. 장문·숫자·혼합언어에서 특히. 스트리밍은 문장 끝을 모른 채 운율을 계획해야 해서 오프라인 대비 품질 격차 |
| ⑦ | **데이터·평가 이중 병목** | 자발화(웃음·머뭇거림) 표현 데이터 희소. MOS는 포화 — "대화에 적절한 운율인가"를 재는 지표가 없음 (2026년 Full-Duplex-Bench류 벤치마크가 나오기 시작한 이유) |
| ⑧ | **캐릭터 매너리즘** | 음색 클로닝 ≠ 인격. "그 캐릭터 특유의 웃음, 말버릇, 추임새"까지 일관된 목소리 인격은 아무도 잘 못 만듦. **연구가 얇은 지점 = 기회** |

---

## 2. 공부할 연구 지도

### 핵심 5축 (순서대로 쌓기)

| 축 | 내용 | 왜 필요한가 |
|---|---|---|
| 1. **뉴럴 오디오 코덱 · 이산 토큰** | EnCodec, DAC, SNAC, Mimi · RVQ · semantic vs acoustic 토큰 | 모든 현대 오디오 LM의 알파벳 |
| 2. **Speech LM 패러다임** | AudioLM → VALL-E → Bark → Orpheus/CSM 계보 (+ 비자기회귀 대안: flow matching — Voicebox, F5-TTS, CosyVoice 디코더) | 파인튜닝할 모델들의 본체 |
| 3. **표현·제어 계보** | GST/reference encoder → PromptTTS/Parler(자연어 스타일) → instruct-TTS → 세밀 비언어 제어 + 감정 disentanglement | "웃을 줄 아는 목소리"의 직접 재료 (한계 ③④) |
| 4. **대화 문맥 합성 (CSS) + CoT-TTS** | 문맥 그래프 모델링, 대화 지식 검색-주입, CoT 스타일 추론 | "10분 내내 같은 사람" — **목표의 본체** (한계 ①②) |
| 5. **음성 후학습 (RLHF/DPO for speech)** | SpeechAlign, Seed-TTS의 RL, 음성 선호도 최적화 | supervised 상한 너머의 "사람같음". SLURM으로 실행 가능한 영역 |

### 지원 3축

| 축 | 내용 | 비고 |
|---|---|---|
| 6. **데이터 엔지니어링** | WhisperX 정렬, 웃음/이벤트 검출, speech captioning, Emilia류 마이닝 파이프라인 | **사실상 프로젝트의 해자** (한계 ⑦) |
| 7. **효율 추론** | 양자화(GGUF/AWQ), 증류(consistency distillation), speculative/streaming decoding | 4060 8GB 제약 대응 |
| 8. **평가 방법론** | UTMOS류 자동지표, speaker sim, CMOS 설계, Full-Duplex-Bench류 | 과학적으로 반복하려면 필수 |

### 장기 (종착점): 풀듀플렉스 S2S

채팅에 반응하는 버튜버의 궁극형은 TTS가 아니라 **"들으면서 말하는 모델"**.

- **Moshi** (Kyutai) — 아키텍처 교과서로 필독. 7B + Mimi 코덱, 이론 160ms
- **PersonaPlex** — 풀듀플렉스에 음성+역할 제어 (AI 버튜버와 정확히 같은 문제의식)
- **Voila** — 음성 롤플레이 특화

지금은 캐스케이드(LLM→태그→TTS)로 시작하되, 이 축을 공부해두면 나중에 합류 가능.

---

## 3. 프로젝트 로드맵 매핑

| 단계 | 할 일 | 필요한 축 |
|---|---|---|
| **A. 무학습 통합** | Orpheus/Chatterbox를 `backend/tts.py` 백엔드로 추가, 4060 실측 | 축 1–2 개념 |
| **B. 보이스 정체성** | AiCy 전용 목소리 — 클로닝 / LoRA (SLURM) | 클로닝·PEFT 실습 |
| **C. 표현 파인튜닝** | 태깅된 표현 데이터로 LoRA → 양자화 → 로컬 배포 | 축 3 + 6 |
| **D. 연구급** | 음성 DPO, 대화 문맥 운율(이전 턴 조건화) | 축 4 + 5 + 8 |
| **종착** | 풀듀플렉스 전환 검토 | Moshi/PersonaPlex 계보 |

### 공부 방법

**코드-퍼스트.** 논문부터 읽지 말고 Orpheus/CSM 코드베이스를 SLURM에서 직접 LoRA
파인튜닝하면서, 막히는 지점이 생길 때 해당 논문을 역으로 읽는 게 훨씬 빠름.
고전(Tacotron2, FastSpeech2, VITS)은 개념만 훑기 — 현역 패러다임은 축 2부터.

### 로컬 후보 모델 (참고 — 영어 품질 우선)

| 순위 | 모델 | 왜 | 4060 추론 |
|---|---|---|---|
| 1 | **Orpheus 3B** (Apache-2.0) | `<laugh>` 등 태그 + Llama 백본이라 LLM 파인튜닝·DPO 기법 그대로 적용 | Q4 양자화(~2GB), 속도는 실시간 경계 — 실측 필요 |
| 2 | **Dia 1.6B** (Apache-2.0) | 대화체 비언어 표현 아웃오브박스 최강 | 8GB 빠듯 → 양자화 |
| 3 | **Chatterbox** (MIT) | 블라인드에서 ElevenLabs 이긴 체감 품질, 감정 과장 조절, 클로닝 내장 | 여유 (실시간 ↑) |
| 4 | **Sesame CSM-1B** (Apache-2.0) | 대화 운율(망설임·페이싱) 특화 — 잡담 톤 | 여유 |
| — | 한국어 확장 시 | CosyVoice2-0.5B (`[laughter]`+instruct, 한국어 O, 공식 LoRA 레시피) / GPT-SoVITS (클로닝) | 여유 |
| ⚠️ | 피할 것 | F5-TTS 기본 ckpt, XTTS-v2, Fish S1-mini 등 **NC(비상업) 가중치** — 수익화 방송과 충돌 | |

---

## Sources

- [ISCSLP 2026 CoT-TTS Challenge](https://arxiv.org/pdf/2606.21933) — 문맥 추론 기반 스타일 결정 (한계 ②)
- [Fine-Grained Non-Verbal Expression Control](https://arxiv.org/html/2605.25504v1) — 비언어 세밀 제어 (한계 ③)
- [Marco-Voice](https://arxiv.org/pdf/2508.02038) — 감정-화자 분리 (한계 ④)
- [RAG 기반 대화 음성합성](https://arxiv.org/pdf/2501.06467) · [문맥 그래프 CSS](https://arxiv.org/pdf/2509.06074) — 대화 문맥 운율 (한계 ①)
- [Moshi (Kyutai)](https://kyutai.org/Moshi.pdf) — 풀듀플렉스 기초 논문 (한계 ⑤)
- [Full-Duplex 동기화·턴테이킹](https://arxiv.org/pdf/2605.20356) — 평가 벤치마크 (한계 ⑦)
- [PersonaPlex](https://arxiv.org/pdf/2602.06053) · [Voila](https://arxiv.org/pdf/2505.02707) — 페르소나 있는 풀듀플렉스
- [CosyVoice2 논문](https://funaudiollm.github.io/pdf/CosyVoice_2.pdf) · [CosyVoice2-0.5B LoRA 사례 (4090 1장)](https://arxiv.org/html/2508.09767v1)
