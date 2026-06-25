"""
우주/코스믹 앰비언트 롱폼 + 숏폼 콘셉트 생성기
2026.06.22 신규

채널 개편 방향:
  - 채널 철학: 우주의 시선으로 보면 지금의 고민은 아무것도 아니야
  - 컨텐츠: 우주/코스믹 앰비언트 단일 파이프라인
  - 음원: Jamendo ambient/atmospheric
  - 영상: Pexels 우주/은하/오로라/성운

제목 포맷: "[감정 카피] | [장르+검색키워드]"
  예) "오늘 밤은 우주 속으로 사라져도 괜찮아 | 수면 명상음악 1시간"
"""

import json
import logging
from pathlib import Path

import anthropic

log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

# ── 카테고리 정의 ──────────────────────────────────────────────────────────

COSMIC_CATEGORIES = [
    "galaxy",   # 은하/딥스페이스
    "aurora",   # 오로라
    "stellar",  # 별/은하수
    "nebula",   # 성운/코스믹
]

# ── Jamendo 설정 ───────────────────────────────────────────────────────────

JAMENDO_SEARCH_TAGS = ["ambient", "sleep", "lullaby"]

_VARTAGS_BASE = ["meditative", "meditation", "calm", "dreamy"]
JAMENDO_REQUIRED_VARTAGS_BY_CATEGORY = {
    "galaxy":  _VARTAGS_BASE,
    "aurora":  _VARTAGS_BASE + ["ambient"],
    "stellar": _VARTAGS_BASE,
    "nebula":  _VARTAGS_BASE + ["dreamy"],
}

JAMENDO_EXCLUDE_TAGS = ["upbeat", "dance", "pop", "rock", "jazz", "dark", "eerie"]

# ── Pexels 영상 쿼리 ───────────────────────────────────────────────────────

PEXELS_QUERIES = {
    "galaxy": [
        "deep space galaxy timelapse",
        "milky way timelapse night",
        "galaxy zoom space abstract",
        "universe deep space stars",
        "cosmic space dark background",
    ],
    "aurora": [
        "northern lights aurora timelapse",
        "aurora borealis night sky",
        "aurora timelapse green sky",
        "polar lights night landscape",
        "northern lights reflection water",
    ],
    "stellar": [
        "star trail night sky timelapse",
        "stars timelapse dark sky",
        "night sky milky way stars",
        "starry night landscape timelapse",
        "constellation stars night",
    ],
    "nebula": [
        "nebula cosmos space abstract",
        "colorful nebula space timelapse",
        "cosmic cloud space purple",
        "space nebula motion abstract",
        "interstellar space colorful",
    ],
}

# ── 카테고리 한국어 설명 ───────────────────────────────────────────────────

CATEGORY_KO = {
    "galaxy":  "은하/딥스페이스",
    "aurora":  "오로라",
    "stellar": "별/은하수",
    "nebula":  "성운/코스믹",
}

# ── 제목 뒷부분 SEO 키워드 풀 ─────────────────────────────────────────────
# Claude가 감정 카피 분위기에 맞게 선택

TITLE_BACK_OPTIONS = [
    "수면 명상음악 1시간",
    "코스믹 수면음악",
    "우주 앰비언트 수면음악",
    "별빛 수면음악 1시간",
    "딥슬립 명상음악",
    "수면유도 코스믹 앰비언트",
    "우주 명상음악 1시간",
    "코스믹 앰비언트 힐링음악",
]

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

# ── 카테고리별 음악 특성 힌트 ─────────────────────────────────────────────

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


# ── 카테고리 선택 ─────────────────────────────────────────────────────────

def _pick_category(used_assets_path: Path) -> str:
    """최근 사용 cosmic 카테고리 피해서 순환 선택"""
    if not used_assets_path.exists():
        return COSMIC_CATEGORIES[0]

    content = used_assets_path.read_text(encoding="utf-8").strip()
    if not content:
        return COSMIC_CATEGORIES[0]
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return COSMIC_CATEGORIES[0]

    cosmic_sessions = {k: v for k, v in data.items() if k.startswith("cosmic_")}
    recent = sorted(cosmic_sessions.keys(), reverse=True)[:len(COSMIC_CATEGORIES)]
    used_cats = [cosmic_sessions[s].get("category", "") for s in recent]

    for cat in COSMIC_CATEGORIES:
        if cat not in used_cats:
            log.info(f"Cosmic 카테고리 선택: {cat} (미사용)")
            return cat

    chosen = COSMIC_CATEGORIES[len(recent) % len(COSMIC_CATEGORIES)]
    log.info(f"Cosmic 카테고리 선택: {chosen} (순환)")
    return chosen


def _get_recent_cosmic_titles(used_assets_path: Path, n: int = 10) -> list[str]:
    """최근 cosmic 세션 제목 목록 (중복 방지용)"""
    if not used_assets_path.exists():
        return []
    content = used_assets_path.read_text(encoding="utf-8").strip()
    if not content:
        return []
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []

    cosmic_sessions = {k: v for k, v in data.items() if k.startswith("cosmic_")}
    recent = sorted(cosmic_sessions.keys(), reverse=True)[:n]
    return [cosmic_sessions[s].get("title", "") for s in recent if cosmic_sessions[s].get("title")]


# ── 콘셉트 생성 ───────────────────────────────────────────────────────────

def generate_cosmic_concept(
    api_key: str,
    used_assets_path: Path,
    force_category: str | None = None,
) -> dict:
    """
    Claude Haiku로 우주/코스믹 1h 롱폼 콘셉트 생성

    반환 예시:
    {
        "category": "galaxy",
        "title": "오늘 밤은 우주 속으로 사라져도 괜찮아 | 수면 명상음악 1시간",
        "shorts_title": "잠이 안 와서 틀었다가 잠든 영상",
        "title_sub": "오늘 밤만큼은",
        "subtitle_en": "Drift into the cosmos",
        "shorts_intro": "오늘 밤, 은하수는 2천억 개의 별로 빛나고 있다.",
        "description_ko": "...",
        "description_en": "...",
        "tags": [...],
        "jamendo_tags": [...],
        "jamendo_required_vartags": [...],
        "jamendo_exclude": [...],
        "pexels_queries": [...],
    }
    """
    category = force_category or _pick_category(used_assets_path)
    cat_name = CATEGORY_KO.get(category, category)
    sound_hint = SOUND_HINTS.get(category, "")
    jamendo_vartags = JAMENDO_REQUIRED_VARTAGS_BY_CATEGORY.get(category, _VARTAGS_BASE)
    pexels_q = PEXELS_QUERIES.get(category, [])

    recent_titles = _get_recent_cosmic_titles(used_assets_path)
    recent_str = "\n".join(f"- {t}" for t in recent_titles) or "없음"
    title_back_str = "\n".join(f"- {t}" for t in TITLE_BACK_OPTIONS)

    prompt = f"""너는 한국 유튜브 수면음악 채널 'Calmdromeda'의 콘텐츠 기획자야.
채널 철학: "우주의 분위기 속으로 스며들어 잠드는 경험을 만든다. 고민을 해소해주는 게 아니라, 잠드는 공간을 만드는 것."
채널 컨셉: Calm(잠) + Andromeda(우주) — 잠과 우주, 이 두 가지가 콘텐츠의 전부다.
오늘 업로드할 1시간 우주/코스믹 앰비언트 수면음악 영상의 콘셉트를 만들어줘.

[카테고리] {cat_name}
[사운드 특성] {sound_hint}

[최근 업로드 제목 (겹치면 안 됨)]
{recent_str}

[요구사항]

1. emotion_copy: 제목 앞부분 카피 (30자 이내)
   - 읽자마자 "우주 + 잠" 두 느낌이 동시에 오는 문장
   - 분위기 묘사가 주인공. 직접적 위로·감정 호소·고민 해소 금지
   - 잠들다 / 잠기다 / 빠져들다 / 스며들다 계열 동사 적극 사용
   - 위로는 분위기 속에 자연스럽게 녹아있어도 OK (직접 건네는 건 금지)
   - ✅ 좋은 예: "별빛 속으로 잠겨드는 밤", "은하수를 따라 잠드는 1시간", "우주 끝에서 잠드는 밤", "오늘 밤은 별빛 속으로 잠겨도 괜찮아"
   - ❌ 금지: "사라져도 괜찮아", "내려놓고", "힘들었죠", "쉬어도 괜찮아", 카테고리명 직접 언급
   - ❌ 단어 금지: "극광" (오로라 카테고리여도 "극광" 대신 "오로라" 사용)
   - 최근 제목과 겹치지 않게

2. title_back: 제목 뒷부분 SEO 키워드 (아래 목록에서 emotion_copy 분위기에 맞는 것 1개 선택)
{title_back_str}

3. shorts_intro: 쇼츠 시작 화면 텍스트 4줄 (\n 으로 구분, 각 줄 20자 이내)
   - 잠들기 직전 혹은 꿈에서 깨어난 직후 쓴 일기체
   - "~았다" "~었다" "~인지 모른다" 과거형 일기체 유지
   - 구조: ①시간/장소 불확실 → ②감각 경계 허물어짐 → ③조용한 공간 감각 → ④{cat_name} 연결 담담한 우주 이미지
   - 마지막 줄: 짧고 심플 (예: "별이 많았다." "오로라가 흘렀다." "성운이 피어났다.")
   - 수치/과학 표현 금지, 전문용어 금지, "너/넌" 직접 화법 절대 금지
   - ✅ 예시: "몇 시였는지 모른다.\n눈을 떴는지 감았는지도 몰랐다.\n다만 어딘가 아주 조용한 곳에 있었다.\n별이 많았다."

4. shorts_title: 쇼츠용 감성 제목 (30자 이내, 롱폼 제목과 완전히 다르게)
   - 직접 화법("너/넌") 금지, 상황/현상 묘사로 공감 자극
   - 예: "잠이 안 와서 틀었다가 잠든 영상", "머릿속이 꺼지는 소리"

5. title_sub: 썸네일 상단 짧은 문구 (8자 이내)
   - 예: "오늘 밤만큼은", "지금 이 순간", "별빛 아래서"

6. subtitle_en: 썸네일 영문 감성 문구 (2~4단어, 시적이고 감성적)
   - 직역 금지. 예: "Drift into the cosmos", "Lost among the stars", "Fade into stardust", "Above the noise"

7. description_ko: 한국어 설명 2~3문장 (감성적, 구어체, 일상 언어)
   - 전문 음악 용어 금지 (신디사이저, 드론, 텍스처, 주파수, 앰비언트 등)
   - 소리를 풍경/감각으로 묘사 (예: "조용히 흐르는 음악", "밤하늘 아래 잠겨드는 소리")
   - 읽으면 잠이 올 것 같은 문체
8. description_en: 영문 설명 2~3문장 (글로벌 시청자용)
9. tags: 한국어 위주 10~15개 태그

JSON만 응답:
{{
  "emotion_copy": "...",
  "title_back": "...",
  "shorts_intro": "...",
  "shorts_title": "...",
  "title_sub": "...",
  "subtitle_en": "...",
  "description_ko": "...",
  "description_en": "...",
  "tags": ["...", "..."]
}}"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=MODEL,
            max_tokens=768,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        ai = json.loads(raw.strip())
        log.info(f"Cosmic 콘셉트 생성: {ai.get('emotion_copy', '')} | {ai.get('title_back', '')}")

    except Exception as e:
        log.error(f"Claude API 오류: {e} — 기본 콘셉트 사용")
        ai = {
            "emotion_copy":   "오늘 밤은 우주 속으로 사라져도 괜찮아",
            "title_back":     "수면 명상음악 1시간",
            "shorts_intro":   "몇 시였는지 모른다.\n눈을 떴는지 감았는지도 몰랐다.\n다만 어딘가 아주 조용한 곳에 있었다.\n별이 많았다.",
            "shorts_title":   "잠이 안 와서 틀었다가 잠든 영상",
            "title_sub":      "오늘 밤만큼은",
            "subtitle_en":    "Drift into the cosmos",
            "description_ko": (
                "오늘 하루가 버거웠다면, 잠깐 우주 속으로 사라져도 괜찮아요. "
                "138억 광년의 광활함 속에서 지금의 고민을 잠시 내려놓아 보세요. "
                "1시간 코스믹 앰비언트로 깊은 수면과 명상을 도와드립니다."
            ),
            "description_en": (
                f"1 hour of cosmic {cat_name} ambient for deep sleep and meditation. "
                "Let the vastness of the universe quiet your mind. "
                "Best experienced with headphones in a dark, quiet space."
            ),
            "tags": [],
        }

    # 제목 조합
    emotion_copy = ai.get("emotion_copy", "오늘 밤은 우주 속으로 사라져도 괜찮아").strip()
    title_back   = ai.get("title_back",   "수면 명상음악 1시간").strip()
    title        = f"{emotion_copy} | {title_back}"
    log.info(f"Cosmic 제목: {title}")

    # 태그 조합
    cat_tags   = CATEGORY_TAGS.get(category, [])
    ai_tags    = ai.get("tags", [])
    merged_tags = list(dict.fromkeys(ai_tags + cat_tags + COMMON_TAGS))[:50]

    # shorts_intro 검증 (1줄 문자열 보장)
    shorts_intro = ai.get("shorts_intro", "")
    if not isinstance(shorts_intro, str) or not shorts_intro.strip():
        shorts_intro = "몇 시였는지 모른다.\n눈을 떴는지 감았는지도 몰랐다.\n다만 어딘가 아주 조용한 곳에 있었다.\n별이 많았다."

    return {
        "category":                 category,
        "title":                    title,
        "shorts_title":             ai.get("shorts_title", ""),
        "title_sub":                ai.get("title_sub", "오늘 밤만큼은"),
        "subtitle_en":              ai.get("subtitle_en", "Drift into the cosmos"),
        "shorts_intro":             shorts_intro,
        "description_ko":           ai.get("description_ko", ""),
        "description_en":           ai.get("description_en", ""),
        "tags":                     merged_tags,
        "jamendo_tags":             JAMENDO_SEARCH_TAGS,
        "jamendo_required_vartags": jamendo_vartags,
        "jamendo_exclude":          JAMENDO_EXCLUDE_TAGS,
        "pexels_queries":           pexels_q,
        "sound_hint":               sound_hint,
    }
