"""
만다라/프랙탈 4h 롱폼 전용 콘셉트 생성기
2026.05.29 신규

대상 포맷: 1시간 롱폼 + 40초 숏폼
카테고리: mandala / fractal / cosmic_meditation
음원 소스: Pixabay Music only (폴백 없음)
"""

import json
import logging
from pathlib import Path

import anthropic

log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

# ── 카테고리 정의 ──────────────────────────────────────────────────────────

MANDALA_CATEGORIES = [
    "mandala",
    "fractal",
    "cosmic_meditation",
]

# Jamendo API 태그 설정
JAMENDO_TAGS_BY_CATEGORY = {
    "mandala":           ["meditation", "calm"],
    "fractal":           ["ambient"],
    "cosmic_meditation": ["dreamy", "ambient"],
}

# 전 카테고리 공통: 음원 장르 태그에 하나라도 포함돼야 함 (OR 조건)
JAMENDO_REQUIRED_TAGS = ["ambient", "new age"]

# 제외 태그
JAMENDO_EXCLUDE_TAGS = ["piano"]

JAMENDO_TAGS_BASE = ["meditation", "ambient", "calm"]  # fallback

# Pexels 영상 쿼리 (만다라/프랙탈/사이키델릭 비주얼)
PEXELS_QUERIES = {
    "mandala": [
        "mandala pattern animation",
        "tibetan mandala geometric",
        "geometric pattern meditation",
        "oriental mandala art",
    ],
    "fractal": [
        "fractal animation psychedelic",
        "mandala fractal pattern",
        "psychedelic visual abstract",
        "geometric fractal motion",
    ],
    "cosmic_meditation": [
        "galaxy timelapse nebula",
        "cosmic space stars",
        "nebula timelapse meditation",
        "milky way stars timelapse",
    ],
}

# 카테고리 한국어 설명
CATEGORY_KO = {
    "mandala":           "만다라 명상",
    "fractal":           "프랙탈 명상",
    "cosmic_meditation": "우주 명상",
}

# 제목 고정 파트 (전 카테고리 공통)
TITLE_PREFIX_KO = "명상음악"
TITLE_PREFIX_EN = "Meditation Music"

# 공통 태그
COMMON_TAGS = [
    "Calmdromeda", "캄드로메다",
    "명상음악", "수면음악", "요가음악", "힐링음악",
    "1시간명상", "딥슬립", "명상", "불면증",
    "Meditation Music", "Sleep Music", "Healing Music",
    "ASMR", "relax", "Deep Sleep", "ambient",
    "yoga music", "meditation", "mandala",
]

# 카테고리별 추가 태그
CATEGORY_TAGS = {
    "mandala":           ["만다라", "만다라명상", "Mandala Meditation", "tibetan mandala", "sacred geometry", "mandala"],
    "fractal":           ["프랙탈", "프랙탈명상", "Fractal Meditation", "psychedelic", "visual meditation", "fractal"],
    "cosmic_meditation": ["우주명상", "코스믹명상", "Cosmic Meditation", "space ambient", "galaxy meditation", "cosmic"],
}

# 카테고리별 사운드 특성 힌트
SOUND_HINTS = {
    "mandala": (
        "만다라를 그리듯 흐르는 명상 음악. "
        "싱잉볼, 동양 악기의 선율이 어우러진 앰비언트 힐링 멜로디. "
        "집중과 이완을 동시에 주는 균형 잡힌 음악."
    ),
    "fractal": (
        "프랙탈 패턴처럼 반복되며 깊어지는 앰비언트 명상음. "
        "사이키델릭하지만 과하지 않은 전자음악 기반 명상 멜로디. "
        "뇌파를 알파/세타파로 유도하는 주파수 대역."
    ),
    "cosmic_meditation": (
        "우주의 광활함을 담은 명상 음악. "
        "신디사이저와 앰비언트 패드가 만드는 무한한 공간감. "
        "별빛 속에서 명상하는 듯한 코스믹 힐링 사운드."
    ),
}


def _pick_category(used_assets_path: Path) -> str:
    """최근 사용 mandala 카테고리 피해서 순환 선택"""
    if not used_assets_path.exists():
        return MANDALA_CATEGORIES[0]

    data = json.loads(used_assets_path.read_text(encoding="utf-8"))
    mandala_sessions = {k: v for k, v in data.items() if k.startswith("mandala_")}
    recent = sorted(mandala_sessions.keys(), reverse=True)[:len(MANDALA_CATEGORIES)]
    used_cats = [mandala_sessions[s].get("category", "") for s in recent]

    for cat in MANDALA_CATEGORIES:
        if cat not in used_cats:
            log.info(f"Mandala 카테고리 선택: {cat} (미사용)")
            return cat

    chosen = MANDALA_CATEGORIES[len(recent) % len(MANDALA_CATEGORIES)]
    log.info(f"Mandala 카테고리 선택: {chosen} (순환)")
    return chosen


def generate_mandala_concept(
    api_key: str,
    used_assets_path: Path,
    force_category: str | None = None,
) -> dict:
    """
    Claude Haiku로 만다라 1h 롱폼 콘셉트 생성

    반환 예시:
    {
        "category": "mandala",
        "title": "명상음악 | 눈을 감으면 보이는 1시간 | Meditation Music - Mandala Deep Relaxation",
        "shorts_title": "멍하니 보다 잠드는 영상",
        "title_sub": "1시간 명상",
        "subtitle_en": "Infinite Bloom",
        "description_en": "...",
        "tags": [...],
        "jamendo_tags": [...],
        "jamendo_exclude": [...],
        "pexels_queries": [...],
    }
    """
    category = force_category or _pick_category(used_assets_path)
    cat_name = CATEGORY_KO.get(category, category)
    sound_hint = SOUND_HINTS.get(category, "")
    jamendo_tags = JAMENDO_TAGS_BY_CATEGORY.get(category, JAMENDO_TAGS_BASE)
    pexels_q = PEXELS_QUERIES.get(category, [])

    recent_titles = _get_recent_mandala_titles(used_assets_path)
    recent_str = "\n".join(f"- {t}" for t in recent_titles) or "없음"

    prompt = f"""너는 한국 유튜브 힐링/명상 채널 'Calmdromeda'의 콘텐츠 기획자야.
오늘 업로드할 1시간 만다라/프랙탈 명상 롱폼 영상의 콘셉트를 만들어줘.

[카테고리] {cat_name}
[사운드 특성] {sound_hint}

[최근 업로드 제목 (겹치면 안 됨)]
{recent_str}

[요구사항]
1. middle_phrase: 중간 감성 문구 (1시간 포함, 20자 이내)
   - 반드시 '1시간' 포함
   - 예: "눈을 감으면 보이는 1시간", "멍하니 보다 잠드는 1시간", "마음이 고요해지는 1시간"
   - 최근 제목과 겹치지 않게
2. seo_keyword: 제목 끝 SEO 영문 키워드 (2~4단어, 카테고리 특성 반영)
   - 예: "Mandala Meditation", "Fractal Ambient Music", "Cosmic Deep Relaxation"
3. shorts_title: 쇼츠용 감성 문구 (30자 이내, "내 얘기다" 느낌)
4. title_sub: 썸네일 상단 짧은 문구 (10자 이내)
5. subtitle_en: 썸네일 하단 영문 (2~4단어, 시적이고 감성적으로)
   - 직역 금지. 예: "Infinite Bloom", "Cosmic Stillness", "Fractal Dreams"
6. description_en: 영문 설명 2~3문장 (글로벌 시청자용, 1시간 강조)
7. tags: 한국어 위주 10~15개

JSON만 응답:
{{
  "middle_phrase": "...",
  "seo_keyword": "...",
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
        log.info(f"Mandala 콘셉트 생성 (raw): {ai.get('middle_phrase', '')} / {ai.get('seo_keyword', '')}")
    except Exception as e:
        log.error(f"Claude API 오류: {e} — 기본 콘셉트 사용")
        ai = {
            "middle_phrase": "마음이 고요해지는 1시간",
            "seo_keyword":   f"{cat_name} Deep Relaxation",
            "shorts_title":  "멍하니 보다 잠드는 영상",
            "title_sub":     "1시간 명상",
            "subtitle_en":   "Infinite Bloom",
            "description_en": (
                f"1 hour of {cat_name} for deep sleep, meditation, and yoga. "
                "Let the visual patterns guide your mind into stillness. "
                "Best experienced in a dark, quiet space."
            ),
            "tags": [],
        }

    # 제목 고정 포맷 조립: 명상음악 | {middle_phrase} | Meditation Music - {seo_keyword}
    middle = ai.get("middle_phrase", "마음이 고요해지는 1시간").strip()
    seo = ai.get("seo_keyword", f"{cat_name} Meditation").strip()
    title = f"{TITLE_PREFIX_KO} | {middle} | {TITLE_PREFIX_EN} - {seo}"
    log.info(f"Mandala 제목: {title}")

    cat_tags = CATEGORY_TAGS.get(category, [])
    ai_tags = ai.get("tags", [])
    merged_tags = list(dict.fromkeys(ai_tags + cat_tags + COMMON_TAGS))[:50]

    return {
        "category":          category,
        "title":             title,
        "shorts_title":      ai.get("shorts_title", ""),
        "title_sub":         ai.get("title_sub", "1시간 명상"),
        "subtitle_en":       ai.get("subtitle_en", "Infinite Bloom"),
        "description_en":    ai.get("description_en", ""),
        "tags":              merged_tags,
        "jamendo_tags":      jamendo_tags,
        "jamendo_required":  JAMENDO_REQUIRED_TAGS,
        "jamendo_exclude":   JAMENDO_EXCLUDE_TAGS,
        "pexels_queries":    pexels_q,
        "duration_hours":    1,
        "sound_hint":        sound_hint,
    }


def _get_recent_mandala_titles(used_assets_path: Path, n: int = 10) -> list[str]:
    if not used_assets_path.exists():
        return []
    data = json.loads(used_assets_path.read_text(encoding="utf-8"))
    mandala_sessions = {k: v for k, v in data.items() if k.startswith("mandala_")}
    recent = sorted(mandala_sessions.keys(), reverse=True)[:n]
    return [mandala_sessions[s].get("title", "") for s in recent if mandala_sessions[s].get("title")]
