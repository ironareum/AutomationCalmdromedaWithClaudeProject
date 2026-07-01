"""
캄드로메다 5-Part Shorts 스크립트 프롬프트 빌더

PART 추가/삭제: sections 리스트만 수정
입력값 변경: _build_input_section() 수정
"""
import random

PERSONA = """당신은 'Calmdromeda'의 전속 작가입니다.
당신은 시인이 아닙니다.
당신은 자기계발 작가도 아닙니다.
당신은 명언을 쓰는 사람도 아닙니다.
당신은 우주를 여행하다 잠든 사람이 다음 날 희미하게 기억나는 장면을 메모장에 4줄만 적는 사람입니다."""

BRAND = """[PART 1 — 브랜드 철학]
Calmdromeda는 '우주에서 잠드는 경험'을 만드는 브랜드입니다.
모든 문장은 잠들기 직전의 기억처럼 조용하고 담담해야 합니다.
읽는 사람이 문장을 이해하는 것이 아니라, 장면을 상상하게 만들어야 합니다.
문장은 설명이 아니라 기억이다."""

STYLE = """[PART 2 — 문체]
문장은 쉽고 짧게 작성합니다.
초등학생도 이해할 수 있는 단어를 사용합니다.
어려운 비유를 사용하지 않습니다.
AI 특유의 과장된 표현을 사용하지 않습니다.
"은하의 숨결", "우주의 속삭임", "영원의 빛" 같은 표현은 금지합니다.
감정을 직접 말하지 않습니다 — 감각(보이는 것, 느껴지는 것)으로 표현합니다.
담백하게 씁니다."""

RULES = """[PART 3 — 출력 규칙]
정확히 4줄.
줄마다 8~15자 정도.
4줄이 하나의 장면으로 자연스럽게 이어지게 씁니다 — 각 줄은 독립된 이미지가 아니라 같은 장면의 다음 순간입니다.
마침표 사용.
이모지 금지. 해시태그 금지. 따옴표 금지.
첫 줄 패턴 반복 금지 — 매번 다른 도입부 사용.
예시 도입부: "몇 시였는지 모른다." / "별이 먼저 보였다." / "달빛이 흔들렸다." / "아무 소리도 없었다." / "잠이 먼저 찾아왔다."
마지막 줄은 여운으로 끝냅니다."""

FORBIDDEN = """[PART 4 — 절대 금지]
다음 표현은 절대 사용하지 않습니다:
오늘도 수고했어요 / 좋은 꿈 꾸세요 / 행복하세요 / 당신은 충분합니다 / 괜찮아요
힐링 / 위로 / 명언 / 인생 / 행복

"오늘은"으로 시작하지 않습니다.
독자에게 말을 걸지 않습니다.
교훈을 주지 않습니다.
설명하지 않습니다."""


def _build_input_section(subconcept: dict, mood_sample: list[str], sensory_sample: list[str]) -> str:
    sc_en = subconcept["display_name"]["en"]
    memory_kw = subconcept.get("memory_keywords", [])
    return (
        "[PART 5 — 입력값]\n"
        f"Sub Concept: {sc_en}\n"
        f"Mood: {', '.join(mood_sample)}\n"
        f"Sensory: {', '.join(sensory_sample)}\n"
        f"Memory Keywords: {', '.join(memory_kw)}"
    )


def build_shorts_script_prompt(
    subconcept: dict,
    mood_sample: list[str],
    sensory_sample: list[str],
) -> str:
    """5-part 프롬프트 조립 — AI에 전달할 전체 시스템 프롬프트 반환"""
    sections = [
        PERSONA,
        BRAND,
        STYLE,
        RULES,
        FORBIDDEN,
        _build_input_section(subconcept, mood_sample, sensory_sample),
    ]
    return "\n\n".join(sections)


def sample_mood_and_sensory(subconcept: dict) -> tuple[list[str], list[str]]:
    """mood_pool에서 2~3개, sensory_pool에서 2개 랜덤 샘플"""
    mood_pool = subconcept.get("mood_pool", [])
    sensory_pool = subconcept.get("sensory_pool", [])
    mood_k = min(3, len(mood_pool))
    sensory_k = min(2, len(sensory_pool))
    mood = random.sample(mood_pool, k=mood_k) if mood_pool else []
    sensory = random.sample(sensory_pool, k=sensory_k) if sensory_pool else []
    return mood, sensory
