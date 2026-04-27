"""
Zen/Oriental 롱폼 전용 콘셉트 생성기
2026.04.27 신규 — pipeline_zen.py 전용

대상 포맷: 8시간 롱폼 + 60초 숏폼
카테고리: moktak_melodic / tibetan_bowl / temple_chant / zen_instrumental / oriental_ambient
음원 소스: Jamendo Music(기본) → Freesound(폴백)
"""

import json
import logging
import os
from datetime import date
from pathlib import Path

import anthropic

log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

# ── 카테고리 정의 ──────────────────────────────────────────────────────────

ZEN_CATEGORIES = [
    "moktak_melodic",
    "tibetan_bowl",
    "temple_chant",
    "zen_instrumental",
    "oriental_ambient",
]

# Jamendo Music API 태그 쿼리 (기본 음원 소스)
# Jamendo API는 space로 구분된 AND 태그 검색 — 최대 3개 권장
JAMENDO_QUERIES = {
    "moktak_melodic":   ["meditation bells zen", "tibetan meditation", "buddhist bells"],
    "tibetan_bowl":     ["tibetan singing bowl", "crystal bowl meditation", "singing bowl"],
    "temple_chant":     ["buddhist chanting", "om meditation", "monk chanting"],
    "zen_instrumental": ["bamboo flute zen", "japanese flute meditation", "koto relaxing"],
    "oriental_ambient": ["asian meditation", "oriental ambient", "zen ambient"],
}

# Freesound 폴백 쿼리 (Pixabay 실패 시)
# - music/melody/composition 키워드 우선 → SFX가 아닌 긴 멜로딕 트랙 타겟
# - loopable/loop 키워드로 루프에 적합한 트랙 유도
FREESOUND_FALLBACK = {
    "moktak_melodic":   ["tibetan singing bowl music loop", "buddhist meditation music bells", "singing bowl meditation music long"],
    "tibetan_bowl":     ["singing bowl meditation music", "tibetan bowl music healing loop", "crystal singing bowl music ambient"],
    "temple_chant":     ["buddhist chanting music loop", "om chanting meditation music", "tibetan monk chanting music"],
    "zen_instrumental": ["bamboo flute music meditation loop", "shakuhachi meditation music", "koto music zen ambient loop"],
    "oriental_ambient": ["asian meditation music ambient loop", "zen music oriental ambient", "chinese meditation music loop"],
}

# Pexels 영상 쿼리 (모든 카테고리 공통 + 신비로운/몽환적 분위기 강화)
PEXELS_QUERIES_COMMON = [
    "night sky stars timelapse",
    "milky way galaxy slow",
    "aurora night sky",
    "candle flame dark background",
    "firefly night forest",
    "fog mist dark forest night",
    "temple incense smoke",
    "singing bowl close up",
    "incense smoke dark",
    "lotus pond still",
    "misty mountain asia",
    "zen garden water",
]

# 카테고리 한국어 설명
CATEGORY_KO = {
    "moktak_melodic":   "목탁 멜로딕 명상음",
    "tibetan_bowl":     "티베탄 싱잉볼",
    "temple_chant":     "사찰 챈팅 명상",
    "zen_instrumental": "선율 명상 악기",
    "oriental_ambient": "오리엔탈 앰비언트",
}

# 카테고리별 제목 앞 키워드
TITLE_KEYWORDS = {
    "moktak_melodic":   "목탁 소리 명상",
    "tibetan_bowl":     "싱잉볼 명상",
    "temple_chant":     "사찰 명상",
    "zen_instrumental": "선율 명상음악",
    "oriental_ambient": "오리엔탈 명상",
}

# 공통 태그
COMMON_TAGS = [
    "Calmdromeda", "캄드로메다",
    "명상음악", "수면음악", "요가음악", "힐링음악",
    "8시간수면음악", "딥슬립", "명상", "불면증",
    "Meditation Music", "Sleep Music", "Healing Music",
    "ASMR", "relax", "Deep Sleep", "ambient",
    "yoga music", "zen music", "meditation",
]

# 카테고리별 추가 태그
CATEGORY_TAGS = {
    "moktak_melodic":   ["목탁소리", "사찰ASMR", "Korean temple", "Buddhist meditation"],
    "tibetan_bowl":     ["싱잉볼", "티베탄볼", "singing bowl", "tibetan bowl", "crystal bowl"],
    "temple_chant":     ["사찰챈팅", "범패", "Buddhist chanting", "om meditation", "chanting"],
    "zen_instrumental": ["대금", "가야금", "bamboo flute", "koto", "zen music", "asian flute"],
    "oriental_ambient": ["오리엔탈", "동양음악", "oriental music", "asian ambient", "zen ambient"],
}

# 카테고리별 사운드 특성 (AI 프롬프트 힌트)
SOUND_HINTS = {
    "moktak_melodic":   "목탁 리듬과 싱잉볼이 어우러진 멜로딕 명상음. 규칙적인 타격음이 뇌파를 안정시키는 느낌. 무아지경으로 빠져드는 리드미컬한 구조.",
    "tibetan_bowl":     "티베탄 싱잉볼의 깊고 울림 있는 배음. 오버톤이 풍부한 투명하고 신성한 소리. 시간이 멈춘 듯한 고요함.",
    "temple_chant":     "불교 챈팅/범패의 깊고 반복적인 음조. 심신을 안정시키는 주기적 리듬. 공간감이 느껴지는 울림.",
    "zen_instrumental": "대나무 피리/가야금 등 동양 악기의 선율적 명상음. 단순하고 반복적인 멜로디로 잡념을 지우는 효과. 자연과 어우러지는 소리.",
    "oriental_ambient": "동양적 분위기의 앰비언트 음악. 멜로딕하면서도 너무 자극적이지 않은 배경음. 요가/명상/수면 모두에 적합한 균형.",
}


def _pick_category(used_assets_path: Path) -> str:
    """최근 사용 zen 카테고리 피해서 순환 선택"""
    if not used_assets_path.exists():
        return ZEN_CATEGORIES[0]

    data = json.loads(used_assets_path.read_text(encoding="utf-8"))
    # zen 세션만 필터 (session_id에 'zen_' prefix 붙임)
    zen_sessions = {k: v for k, v in data.items() if k.startswith("zen_")}
    recent = sorted(zen_sessions.keys(), reverse=True)[:len(ZEN_CATEGORIES)]
    used_cats = [zen_sessions[s].get("category", "") for s in recent]

    for cat in ZEN_CATEGORIES:
        if cat not in used_cats:
            log.info(f"Zen 카테고리 선택: {cat} (미사용)")
            return cat

    # 전부 사용됐으면 가장 오래된 것
    chosen = ZEN_CATEGORIES[len(recent) % len(ZEN_CATEGORIES)]
    log.info(f"Zen 카테고리 선택: {chosen} (순환)")
    return chosen


def generate_zen_concept(
    api_key: str,
    used_assets_path: Path,
    force_category: str | None = None,
) -> dict:
    """
    Claude Haiku로 zen 롱폼 콘셉트 생성

    반환 예시:
    {
        "category": "moktak_melodic",
        "title": "목탁 소리 명상 | 잡생각이 사라지는 8시간 | Temple Bells - Deep Sleep Meditation",
        "shorts_title": "잠이 안 올 때 이 소리만 틀어요",
        "title_sub": "8시간 명상",
        "subtitle_en": "Drift Into Stillness",
        "description_en": "...",
        "tags": [...],
        "pixabay_queries": [...],
        "freesound_fallback": [...],
        "pexels_queries": [...],
    }
    """
    category = force_category or _pick_category(used_assets_path)
    cat_name = CATEGORY_KO.get(category, category)
    title_kw = TITLE_KEYWORDS.get(category, cat_name)
    sound_hint = SOUND_HINTS.get(category, "")
    jamendo_q = JAMENDO_QUERIES.get(category, [])
    freesound_q = FREESOUND_FALLBACK.get(category, [])

    # 최근 zen 제목 참조 (중복 방지)
    recent_titles = _get_recent_zen_titles(used_assets_path)
    recent_str = "\n".join(f"- {t}" for t in recent_titles) or "없음"

    prompt = f"""너는 한국 유튜브 힐링/명상 채널 'Calmdromeda'의 콘텐츠 기획자야.
오늘 업로드할 8시간 명상 롱폼 영상의 콘셉트를 만들어줘.

[카테고리] {cat_name}
[사운드 특성] {sound_hint}

[최근 업로드 제목 (겹치면 안 됨)]
{recent_str}

[요구사항]
1. title: "{title_kw} | 감성 문구 (8시간 포함) | 영문 - SEO키워드" 형식 (100자 이내)
   - 반드시 "{title_kw}"로 시작
   - 중간 감성 문구에 '8시간' 반드시 포함
     예: "잡생각이 사라지는 8시간", "잠들 때까지 듣는 8시간", "머리가 맑아지는 8시간"
   - 마지막 파트: "썸네일 영문(2단어) - SEO 영문키워드"
   - 예: "{title_kw} | 잡생각이 사라지는 8시간 | Temple Bells - Deep Sleep Meditation Music"
2. shorts_title: 쇼츠용 감성 문구 (30자 이내, "내 얘기다" 느낌)
   - 예: "잡생각이 많을 땐 이 소리만 들어요"
3. title_sub: 썸네일 상단 짧은 문구 (10자 이내)
4. subtitle_en: 썸네일 하단 영문 (2~4단어, 시적이고 감성적으로)
   - 직역 금지. 예: "Drift Into Stillness", "Ancient & Calm", "Temple of Quiet"
5. description_en: 영문 설명 2~3문장 (글로벌 시청자용, 8시간 강조)
6. tags: 한국어 위주 10~15개

JSON만 응답:
{{
  "title": "...",
  "shorts_title": "...",
  "title_sub": "...",
  "subtitle_en": "...",
  "description_en": "...",
  "tags": ["...", "..."]
}}"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        ai = json.loads(raw.strip())
        log.info(f"Zen 콘셉트 생성: {ai.get('title', '')}")
    except Exception as e:
        log.error(f"Claude API 오류: {e} — 기본 콘셉트 사용")
        ai = {
            "title": f"{title_kw} | 잡생각이 사라지는 8시간 | Zen Meditation - Deep Sleep Music",
            "shorts_title": "잡생각이 많을 땐 이 소리만 들어요",
            "title_sub": "8시간 명상",
            "subtitle_en": "Drift Into Stillness",
            "description_en": (
                f"8 hours of {cat_name} for deep sleep, meditation, and yoga. "
                "Let the ancient sounds guide your mind into stillness. "
                "Best experienced with headphones in a quiet space."
            ),
            "tags": [],
        }

    cat_tags = CATEGORY_TAGS.get(category, [])
    ai_tags = ai.get("tags", [])
    merged_tags = list(dict.fromkeys(ai_tags + cat_tags + COMMON_TAGS))[:50]

    return {
        "category":          category,
        "title":             ai.get("title", ""),
        "shorts_title":      ai.get("shorts_title", ""),
        "title_sub":         ai.get("title_sub", "8시간 명상"),
        "subtitle_en":       ai.get("subtitle_en", "Ancient & Calm"),
        "description_en":    ai.get("description_en", ""),
        "tags":              merged_tags,
        "jamendo_queries":   jamendo_q,
        "freesound_fallback": freesound_q,
        "pexels_queries":    PEXELS_QUERIES_COMMON,
        "duration_hours":    8,
        "sound_hint":        sound_hint,
    }


def _get_recent_zen_titles(used_assets_path: Path, n: int = 10) -> list[str]:
    if not used_assets_path.exists():
        return []
    data = json.loads(used_assets_path.read_text(encoding="utf-8"))
    zen_sessions = {k: v for k, v in data.items() if k.startswith("zen_")}
    recent = sorted(zen_sessions.keys(), reverse=True)[:n]
    return [zen_sessions[s].get("title", "") for s in recent if zen_sessions[s].get("title")]
