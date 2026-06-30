"""
우주/코스믹 앰비언트 롱폼 + 숏폼 콘셉트 생성기 (v2.0)
2026.06.26 3계층 구조 (Category → Sub Concept → Story) 적용

흐름:
  rotation.py → 카테고리 로테이션 + 서브컨셉 히스토리 선택
  prompt_builder.py → 5-Part 프롬프트 조립
  Claude Haiku → shorts_intro(4줄 기억 조각) + description + tags 생성
  제목: subconcept SEO 기반 고정 포맷
"""

import json
import logging
from pathlib import Path

import anthropic

from planner.rotation import pick_category_and_subconcept
from planner.prompt_builder import build_shorts_script_prompt, sample_mood_and_sensory

log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

TITLE_BACK_FIXED = "1 Hour Ambient Sound"

# ── Jamendo 설정 ───────────────────────────────────────────────────────────

JAMENDO_SEARCH_TAGS = ["ambient", "sleep", "lullaby", "meditation", "relaxing", "atmospheric"]

_VARTAGS_BASE = [
    "ambient", "space", "atmospheric", "slow", "drone", "cinematic",
    "sleep", "calm", "meditation", "dreamy", "relax", "relaxing",
    "ethereal", "floating",
]
JAMENDO_REQUIRED_VARTAGS_BY_CATEGORY = {
    "galaxy":  _VARTAGS_BASE,
    "aurora":  _VARTAGS_BASE,
    "stellar": _VARTAGS_BASE,
    "nebula":  _VARTAGS_BASE,
}

JAMENDO_EXCLUDE_TAGS = ["rock", "pop", "dance", "metal", "punk"]

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
        "shorts_intro": "몇 시였는지 모른다.\n별이 많았다.\n...",
        "description_ko": "...",
        "description_en": "...",
        "tags": [...],
        "jamendo_tags": [...],
        "jamendo_required_vartags": [...],
        "jamendo_exclude": [...],
        "pexels_queries": [...],
    }
    """
    subconcept = pick_category_and_subconcept(used_assets_path, force_category)
    category = subconcept.get("category", "galaxy")

    mood_sample, sensory_sample = sample_mood_and_sensory(subconcept)
    script_prompt = build_shorts_script_prompt(subconcept, mood_sample, sensory_sample)

    sc_en = subconcept["display_name"]["en"]
    sc_ko = subconcept["display_name"]["ko"]
    seo_ko = subconcept["seo"]["ko"]
    seo_en = subconcept["seo"]["en"]

    full_prompt = f"""{script_prompt}

위 규칙으로 shorts_intro(4줄 기억 조각)를 작성하고, 아래 필드도 함께 생성하세요.

longform_emotional: 롱폼 썸네일용 감성 문구 (20자 이내, 한국어, 잠들기 전 기억처럼 담백하게, 독자에게 말 걸기 금지)
  예시: "오로라 따라가다 그냥 잠들었어요" / "별빛이 손가락 사이로 흘렀다" / "우주 끝에서 눈이 감겼다"
shorts_title: 유튜브 쇼츠 제목 (30자 이내, 한국어, 감성적, longform_emotional과 다른 문장, 독자에게 직접 말 걸기 금지)
  예시: "우주 틀었다가 깨보니 새벽이었던 영상"
description_ko: 한국어 롱폼 설명 2문장 (시적, 전문 음악 용어 금지, 소리를 풍경/감각으로 묘사)
shorts_description: 한국어 쇼츠 설명 2~3문장 (몰입감 있는 서술, 보는 사람이 그 공간에 빠져드는 느낌)
tags: {sc_ko}/{sc_en} 관련 태그 5~8개

JSON만 응답:
{{
  "shorts_intro": "줄1\\n줄2\\n줄3\\n줄4",
  "longform_emotional": "...",
  "shorts_title": "...",
  "description_ko": "...",
  "shorts_description": "...",
  "tags": ["...", "..."]
}}"""

    ai = {}
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=MODEL,
            max_tokens=1024,
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
            "shorts_intro":       "몇 시였는지 모른다.\n눈을 떴는지 감았는지도 몰랐다.\n다만 어딘가 아주 조용한 곳에 있었다.\n별이 많았다.",
            "longform_emotional": f"{sc_ko} 따라가다 그냥 잠들었어요",
            "shorts_title":       "잠이 안 와서 틀었다가 잠든 영상",
            "description_ko":     f"조용히 {sc_ko}를 여행하다 잠드는 1시간.",
            "shorts_description": f"말없이 {sc_ko} 속으로 빠져드는 시간이었어요. 생각이 하나둘 사라지고, 어느새 깊은 곳에 있었어요.",
            "tags": [],
        }

    # 제목 조합 — SEO 고정 포맷
    title = f"{seo_ko} | {seo_en} | {TITLE_BACK_FIXED}"
    log.info(f"제목: {title}")

    # 태그 조합
    cat_tags    = CATEGORY_TAGS.get(category, [])
    ai_tags     = ai.get("tags", [])
    merged_tags = list(dict.fromkeys(ai_tags + cat_tags + COMMON_TAGS))[:50]

    # shorts_intro 검증
    shorts_intro = ai.get("shorts_intro", "")
    if not isinstance(shorts_intro, str) or not shorts_intro.strip():
        shorts_intro = "몇 시였는지 모른다.\n눈을 떴는지 감았는지도 몰랐다.\n다만 어딘가 아주 조용한 곳에 있었다.\n별이 많았다."

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
        "shorts_description":       ai.get("shorts_description", ""),
        "tags":                     merged_tags,
        "jamendo_tags":             JAMENDO_SEARCH_TAGS,
        "jamendo_required_vartags": jamendo_vartags,
        "jamendo_exclude":          JAMENDO_EXCLUDE_TAGS,
        "pexels_queries":           subconcept.get("pexels_queries", []),
    }
