"""
우주/코스믹 앰비언트 롱폼 + 숏폼 콘셉트 생성기 (v2.0)
2026.06.26 3계층 구조 (Category → Sub Concept → Story) 적용
2026.06.30 shorts_intro(4줄 고정 포맷) 폐기 — description_ko를 쇼츠 텍스트 오버레이로도 재사용

흐름:
  rotation.py → 카테고리 로테이션 + 서브컨셉 히스토리 선택
  Claude Haiku → longform_emotional + shorts_title + description_ko + tags 생성
  제목: subconcept SEO 기반 고정 포맷
"""

import json
import logging
from pathlib import Path

import anthropic

from planner.rotation import pick_category_and_subconcept

log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

TITLE_BACK_FIXED = "1 Hour Ambient Sound"

# ── Jamendo 설정 ───────────────────────────────────────────────────────────

JAMENDO_SEARCH_TAGS = ["ambient", "sleep", "lullaby", "meditation", "relaxing", "atmospheric"]

_VARTAGS_BASE = [
    "ambient", "space", "atmospheric", "slow", "cinematic",
    "sleep", "calm", "meditation", "dreamy", "relax", "relaxing",
    "ethereal", "floating",
]
JAMENDO_REQUIRED_VARTAGS_BY_CATEGORY = {
    "galaxy":  _VARTAGS_BASE,
    "aurora":  _VARTAGS_BASE,
    "stellar": _VARTAGS_BASE,
    "nebula":  _VARTAGS_BASE,
}

JAMENDO_EXCLUDE_TAGS = ["rock", "pop", "dance", "metal", "punk", "horror", "industrial", "noise", "experimental", "dark", "eerie", "jazz"]

# ── 공통 태그 ─────────────────────────────────────────────────────────────

COMMON_TAGS = [
    "Calmdromeda", "캄드로메다",
    "수면음악", "명상음악", "힐링음악", "불면증",
    "딥슬립", "수면유도", "우주음악", "코스믹",
    "Sleep Music", "Cosmic Ambient", "Space Music",
    "Meditation Music", "Deep Sleep", "Healing Music",
    "ambient", "space ambient", "relaxing",
]

# ── 카테고리별 추가 태그 ──────────────────────────────────────────────────

CATEGORY_TAGS = {
    "galaxy":  ["은하", "딥스페이스", "Galaxy Music", "Deep Space Ambient", "우주힐링"],
    "aurora":  ["오로라", "극광", "Aurora Ambient", "Northern Lights Music", "오로라음악"],
    "stellar": ["별빛", "은하수", "Star Music", "Stellar Ambient", "별소리"],
    "nebula":  ["성운", "코스믹", "Nebula Music", "Cosmic Sounds", "우주명상"],
}

# ── 카테고리별 Jamendo 음악 특성 힌트 ────────────────────────────────────

SOUND_HINTS = {
    "galaxy": (
        "광활한 우주 공간을 떠다니는 느낌의 딥 앰비언트. "
        "저음역의 드론 사운드와 희미한 신디사이저 패드가 깔리는 음악. "
        "속도감 없이 천천히 흐르는 무한한 공간감."
    ),
    "aurora": (
        "오로라처럼 흐르고 물결치는 앰비언트 사운드. "
        "밝고 신비로운 신디사이저 멜로디가 대기 속을 유영하는 느낌. "
        "차갑고 투명하지만 따뜻한 감성이 공존하는 음악."
    ),
    "stellar": (
        "별빛이 조용히 쏟아지는 밤하늘 같은 앰비언트. "
        "섬세하고 잔잔한 신디사이저 텍스처, 별빛처럼 간간이 빛나는 톤. "
        "깊은 밤의 고요함과 우주적 평온함을 담은 음악."
    ),
    "nebula": (
        "성운의 가스와 빛이 뒤섞이는 사이키델릭한 앰비언트. "
        "다채로운 색감처럼 레이어가 겹치는 신디사이저 사운드. "
        "몽환적이지만 과하지 않은, 신비롭고 깊은 우주 사운드."
    ),
}


# ── 콘셉트 생성 ───────────────────────────────────────────────────────────

def generate_cosmic_concept(
    api_key: str,
    used_assets_path: Path,
    force_category: str | None = None,
    extra_exclude_ids: list | None = None,
) -> dict:
    """
    3계층 구조 기반 코스믹 콘셉트 생성

    반환 예시:
    {
        "category": "galaxy",
        "subconcept_id": "milky_way",
        "subconcept_en": "Milky Way",
        "subconcept_ko": "은하수",
        "subconcept_color": "#5B7FFF",
        "title": "은하수 수면음악 | Milky Way Sleep Music | 1 Hour Ambient Sound",
        "shorts_title": "잠이 안 와서 틀었다가 잠든 영상",
        "description_ko": "...",
        "tags": [...],
        "jamendo_tags": [...],
        "jamendo_required_vartags": [...],
        "jamendo_exclude": [...],
        "pexels_queries": [...],
    }
    """
    subconcept = pick_category_and_subconcept(used_assets_path, force_category, extra_exclude_ids=extra_exclude_ids)
    category = subconcept.get("category", "galaxy")

    sc_en = subconcept["display_name"]["en"]
    sc_ko = subconcept["display_name"]["ko"]
    seo_ko = subconcept["seo"]["ko"]
    seo_en = subconcept["seo"]["en"]

    full_prompt = f"""당신은 'Calmdromeda'의 전속 작가입니다.
Calmdromeda는 '우주에서 잠드는 경험'을 만드는 브랜드입니다.
모든 문장은 잠들기 직전의 기억처럼 조용하고 담담해야 합니다.
초등학생도 이해할 수 있는 쉬운 단어를 쓰고, 어려운 비유나 전문 음악 용어는 쓰지 않습니다.
감정을 직접 말하지 않고 감각(보이는 것, 느껴지는 것)으로 표현합니다.

Sub Concept: {sc_en} ({sc_ko})

아래 필드를 생성하세요.

longform_emotional: 롱폼 썸네일용 감성 문구 (20자 이내, 한국어, 잠들기 전 기억처럼 담백하게, 독자에게 말 걸기 금지)
  예시: "오로라 따라가다 그냥 잠들었어요" / "별빛이 손가락 사이로 흘렀다" / "우주 끝에서 눈이 감겼다"
shorts_title: 유튜브 쇼츠 제목 (30자 이내, 한국어, 감성적, longform_emotional과 다른 문장, 독자에게 직접 말 걸기 금지)
  예시: "우주 틀었다가 깨보니 새벽이었던 영상"
shorts_intro: 쇼츠 영상 텍스트 오버레이용, 정확히 4줄 (한국어) — 우주를 여행하다 잠든 사람이 다음 날 희미하게 기억나는 장면을 메모장에 4줄만 적는 느낌
  줄마다 8~15자 정도로 짧게 씁니다.
  4줄이 하나의 장면으로 자연스럽게 이어지게 씁니다 — 각 줄은 독립된 이미지가 아니라 같은 장면의 다음 순간입니다.
  마침표로 끝냅니다. 이모지·해시태그·따옴표 금지.
  첫 줄 패턴을 반복하지 않습니다 — 매번 다른 도입부를 씁니다.
  "오늘도 수고했어요", "좋은 꿈 꾸세요", "힐링", "위로", "명언" 같은 표현은 금지합니다. 독자에게 말을 걸거나 교훈을 주지 않습니다.
  "은하의 숨결", "우주의 속삭임", "영원의 빛" 같은 AI 특유의 과장된 클리셰 표현은 금지합니다.
  예시: "몇 시였는지 모른다.\\n별이 먼저 보였다.\\n바람이 차갑게 스쳤다.\\n어느새 눈이 감겨 있었다."
description_ko: 한국어 설명 2~3문장 (몰입감 있는 서술, 보는 사람이 그 공간에 빠져드는 느낌) — 롱폼 영상 설명란에 사용됩니다
  문장은 짧고 담백한 단문으로 씁니다.
  한 문장에 비유(직유/은유)는 최대 1개까지만 사용합니다 — 여러 비유를 한 문장에 겹치지 않습니다.
  "은하의 숨결", "우주의 속삭임", "영원의 빛" 같은 AI 특유의 과장된 클리셰 표현은 금지합니다.
  전문 음악 용어는 쓰지 않습니다.
  예시 (이 정도의 절제된 톤을 유지하세요): "언제부터였는지 모른다. 눈이 감겼는지 떠있었는지도 몰랐다. 다만 아주 깊고 조용한 곳에 있었다. 은하가 천천히 흐르고 있었다."
tags: {sc_ko}/{sc_en} 관련 태그 5~8개

JSON만 응답:
{{
  "longform_emotional": "...",
  "shorts_title": "...",
  "shorts_intro": "줄1\\n줄2\\n줄3\\n줄4",
  "description_ko": "...",
  "tags": ["...", "..."]
}}"""

    ai = {}
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=MODEL,
            max_tokens=768,
            messages=[{"role": "user", "content": full_prompt}]
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        ai = json.loads(raw.strip())
        log.info(f"콘셉트 생성: {sc_en} / {ai.get('shorts_title', '')}")

    except Exception as e:
        log.error(f"Claude API 오류: {e} — 기본 콘셉트 사용")
        ai = {
            "longform_emotional": f"{sc_ko} 따라가다 그냥 잠들었어요",
            "shorts_title":       "잠이 안 와서 틀었다가 잠든 영상",
            "shorts_intro":       "몇 시였는지 모른다.\n눈을 떴는지 감았는지도 몰랐다.\n다만 어딘가 아주 조용한 곳에 있었다.\n별이 많았다.",
            "description_ko":     f"말없이 {sc_ko} 속으로 빠져드는 시간이었어요. 생각이 하나둘 사라지고, 어느새 깊은 곳에 있었어요.",
            "tags": [],
        }

    # 제목 조합 — SEO 고정 포맷
    title = f"{seo_ko} | {seo_en} | {TITLE_BACK_FIXED}"
    log.info(f"제목: {title}")

    # 태그 조합
    cat_tags    = CATEGORY_TAGS.get(category, [])
    ai_tags     = ai.get("tags", [])
    merged_tags = list(dict.fromkeys(ai_tags + cat_tags + COMMON_TAGS))[:50]

    # shorts_intro 검증 — 4줄 아니면 에러 (동일 기본 텍스트가 반복 노출되는 것을 방지)
    shorts_intro = ai.get("shorts_intro", "")
    if not isinstance(shorts_intro, str) or len([l for l in shorts_intro.split("\n") if l.strip()]) != 4:
        raise ValueError(f"shorts_intro 형식 오류 — 4줄이 아님: {shorts_intro!r}")

    jamendo_vartags = JAMENDO_REQUIRED_VARTAGS_BY_CATEGORY.get(category, _VARTAGS_BASE)

    return {
        "category":                 category,
        "subconcept_id":            subconcept.get("id", ""),
        "subconcept_en":            sc_en,
        "subconcept_ko":            sc_ko,
        "seo_ko":                   seo_ko,
        "seo_en":                   seo_en,
        "subconcept_color":         subconcept.get("color", "#5B7FFF"),
        "title":                    title,
        "longform_emotional":       ai.get("longform_emotional", f"{sc_ko}"),
        "shorts_title":             ai.get("shorts_title", ""),
        "shorts_intro":             shorts_intro,
        "description_ko":           ai.get("description_ko", ""),
        "tags":                     merged_tags,
        "jamendo_tags":             JAMENDO_SEARCH_TAGS,
        "jamendo_required_vartags": jamendo_vartags,
        "jamendo_exclude":          JAMENDO_EXCLUDE_TAGS,
        "pexels_queries":           subconcept.get("pexels_queries", []),
    }
