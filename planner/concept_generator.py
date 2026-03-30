"""
AI 콘셉트 자동 생성기
2026.03.29 Claude Haiku API로 매일 새로운 영상 콘셉트 자동 생성

[고려 요소]
- 계절/날씨 반영 (오늘 날짜 기준)
- 카테고리 로테이션 (최근 업로드와 중복 방지)
- 기존 업로드 영상 제목과 겹치지 않게
- 한국어 타겟 (제목/태그 한국어)

2026.03.30 사운드 쿼리 로직 변경 - 사운드 쿼리 풀에서 AI가 콘셉트/계절에 맞는 것만 골라옴
2026.03.30 신규 신규 카테고리 추가(12개)
2026.03.30 pick_category 로직 변경(랜덤방식, 추적 갯수 변경(기존:7 -> 변경:전체 카테고리 개수의 절반)
"""

import json
import logging
import os
import random
from datetime import datetime, date
from pathlib import Path

import anthropic

log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

# 지원 카테고리 전체 목록
ALL_CATEGORIES = [
    "rain", "rain_thunder", "ocean", "forest", "birds",
    "white_noise", "cafe", "camping",
    "airplane", "subway", "library", "underwater",
    "hot_spring", "fireplace_rain", "summer_night",
    "winter_snow", "study_room", "stream",
    "summer_rain", "snow_walk",
]

# 카테고리별 한국어 설명 (프롬프트용)
CATEGORY_KO = {
    "rain":         "빗소리",
    "rain_thunder": "빗소리+천둥",
    "ocean":        "파도/바다소리",
    "forest":       "숲 자연소리",
    "birds":        "새소리",
    "white_noise":  "백색소음",
    "cafe":         "카페 분위기",
    "camping":      "캠핑/모닥불",
    "airplane":     "비행기 기내소음",
    "subway":       "지하철/기차 소음",
    "library":      "도서관/독서실",
    "underwater":   "수족관/바닷속",
    "hot_spring":   "온천/물소리",
    "fireplace_rain": "모닥불+빗소리",
    "summer_night": "여름밤 귀뚜라미",
    "winter_snow":  "겨울 눈 내리는 소리",
    "study_room":   "공부방 분위기",
    "stream":       "계곡/시냇물",
}

# 카테고리별 Freesound 검색 쿼리
# 카테고리별 기본 영상 쿼리 (Claude 프롬프트 힌트용)
CATEGORY_VIDEO_QUERIES = {
    "rain": [
        "rain window", "rainy day", "rain drops glass",
        "rain street", "rain nature", "spring rain window",
        "rain forest", "rainy night city", "rain puddle"
    ],
    "rain_thunder": [
        "thunderstorm", "lightning rain", "dark storm",
        "storm clouds", "lightning sky", "dramatic storm"
    ],
    "ocean": [
        "ocean waves", "beach waves", "calm sea",
        "sunset beach waves", "coastal landscape", "sea shore",
        "spring beach", "peaceful ocean", "ocean horizon"
    ],
    "forest": [
        "forest nature", "misty forest", "green forest",
        "forest path", "woodland morning", "forest sunlight",
        "forest stream", "autumn forest", "spring forest"
    ],
    "birds": [
        "birds nature", "morning forest", "peaceful garden",
        "birds flying", "meadow nature", "bird wildlife"
    ],
    "white_noise": [
        "abstract calm", "minimalist nature", "soft light",
        "peaceful landscape", "calm water", "zen nature"
    ],
    "cafe": [
        "cafe window", "coffee shop", "cozy interior",
        "cafe rain", "warm interior", "coffee morning"
    ],
    "camping": [
        "campfire night", "tent camping", "forest night",
        "campfire outdoor", "starry night camping", "bonfire nature"
    ],
}

# 카테고리별 검증된 Freesound 쿼리 풀
# AI는 이 목록 안에서만 3개 선택 → 엉뚱한 키워드 방지
CATEGORY_SOUNDS = {
    "rain": [
        "heavy rain", "rain on window", "gentle rain",
        "soft rain", "rain drops", "rain forest",
        "rainy night", "spring rain", "light rain",
        "rain storm", "rain roof", "rainfall nature"
    ],
    "rain_thunder": [
        "thunder storm", "heavy rain thunder", "lightning rain",
        "thunderstorm rain", "distant thunder", "storm rain night"
    ],
    "ocean": [
        "ocean waves", "gentle waves", "beach waves",
        "calm sea waves", "ocean shore", "coastal waves",
        "soft ocean waves", "sea water", "waves sandy beach",
        "calm ocean ambient", "ocean sounds relaxing"
    ],
    "forest": [
        "forest ambience", "nature sounds", "forest birds",
        "forest rain", "woodland nature", "forest stream",
        "deep forest", "nature ambience", "forest morning"
    ],
    "birds": [
        "birds chirping", "morning birds", "bird song",
        "birds singing", "birdsong nature", "birds forest",
        "dawn chorus birds", "peaceful birds", "birds meadow"
    ],
    "white_noise": [
        "white noise", "brown noise", "pink noise",
        "fan noise", "static noise", "ambient noise"
    ],
    "cafe": [
        "cafe ambience", "coffee shop", "indoor ambience",
        "cafe background", "coffee shop noise", "cafe rain window"
    ],
    "camping": [
        "campfire", "forest night", "crickets night",
        "campfire crackling", "night forest", "fire crackling outdoor"
    ],
}


def _get_season(today: date) -> str:
    m = today.month
    if m in (3, 4, 5):   return "봄"
    if m in (6, 7, 8):   return "여름"
    if m in (9, 10, 11): return "가을"
    return "겨울"


def _get_recent_categories(used_assets_path: Path, n: int = None) -> list[str]:
    """
    최근 N개 세션에서 사용한 카테고리 목록 반환
    n 기본값: 카테고리 수의 절반 (20개면 10개 추적)
    """
    if n is None:
        n = max(7, len(ALL_CATEGORIES) // 2)
    if not used_assets_path.exists():
        return []
    data = json.loads(used_assets_path.read_text(encoding="utf-8"))
    # session_id 최신순 정렬
    recent = sorted(data.keys(), reverse=True)[:n]
    categories = []
    for sid in recent:
        entry = data[sid]
        # 제목에서 카테고리 추론 (sounds 파일명 기반)
        sounds = entry.get("sounds", [])
        for cat, queries in CATEGORY_SOUNDS.items():
            if any(any(q.split()[0] in s.lower() for q in queries) for s in sounds):
                if cat not in categories:
                    categories.append(cat)
    return categories


def _get_recent_titles(used_assets_path: Path, n: int = 14) -> list[str]:
    """최근 N개 세션의 제목 목록 반환"""
    if not used_assets_path.exists():
        return []
    data = json.loads(used_assets_path.read_text(encoding="utf-8"))
    recent = sorted(data.keys(), reverse=True)[:n]
    return [data[sid].get("title", "") for sid in recent if data[sid].get("title")]


def _pick_category(recent_categories: list[str]) -> str:
    """
    최근에 안 쓴 카테고리 중 랜덤 선택 (공평한 로테이션)
    - 안 쓴 카테고리 있으면 → 그 중 랜덤
    - 전부 최근에 썼으면 → 최근 3개 제외하고 랜덤
    """
    unused = [c for c in ALL_CATEGORIES if c not in recent_categories]
    if unused:
        chosen = random.choice(unused)
        log.info(f"카테고리 선택: {chosen} (미사용 {len(unused)}개 중 랜덤)")
        return chosen
    # 전부 최근에 썼으면 최근 3개만 피하고 랜덤
    available = [c for c in ALL_CATEGORIES if c not in recent_categories[-3:]]
    if available:
        chosen = random.choice(available)
        log.info(f"카테고리 선택: {chosen} (전체 로테이션 완료, 최근 3개 제외 랜덤)")
        return chosen
    return random.choice(ALL_CATEGORIES)


def generate_concept(
    api_key: str,
    used_assets_path: Path,
    duration_hours: float = 1,
    language: str = "ko",
) -> dict:
    """
    Claude Haiku로 오늘의 영상 콘셉트 자동 생성

    반환 예시:
    {
        "title": "빗소리 ASMR | 1시간 숙면 & 집중 사운드 | 공부할 때 듣기 좋은 음악",
        "category": "rain",
        "sounds": ["heavy rain", "rain on window", "gentle rain"],
        "mood": "cozy rainy",
        "duration_hours": 1,
        "title_sub": "공부할 때 듣기 좋은",
        "subtitle_en": "Rain Sounds",
        "tags": ["빗소리", "ASMR", ...],
        "language": "ko"
    }
    """
    today          = date.today()
    season         = _get_season(today)
    recent_cats    = _get_recent_categories(used_assets_path)
    recent_titles  = _get_recent_titles(used_assets_path)
    category       = _pick_category(recent_cats)
    category_name  = CATEGORY_KO.get(category, category)
    sounds         = CATEGORY_SOUNDS.get(category, ["nature sounds"])

    log.info(f"AI 기획 시작 — 카테고리: {category}({category_name}), 계절: {season}")

    # ── 프롬프트 ──────────────────────────────────────────────────────
    recent_titles_str = "\n".join(f"- {t}" for t in recent_titles[:5]) or "없음"

    default_sounds_str = ", ".join(sounds)
    default_videos = CATEGORY_VIDEO_QUERIES.get(category, [category])
    default_videos_str = ", ".join(default_videos)
    prompt = f"""너는 한국 유튜브 힐링/ASMR 채널 'Calmdromeda'의 콘텐츠 기획자야.
오늘 업로드할 자연 사운드 영상의 콘셉트를 만들어줘.

[오늘 정보]
- 날짜: {today.strftime("%Y년 %m월 %d일")} ({season})
- 선택된 카테고리: {category_name}
- 영상 길이: {duration_hours}시간

[최근 업로드 제목 (겹치면 안 됨)]
{recent_titles_str}

[사운드 쿼리 풀 — 이 중에서만 3개 선택]
{default_sounds_str}

[영상 쿼리 풀 — 이 중에서만 3~4개 선택]
{default_videos_str}

[요구사항]
1. 제목은 "메인 키워드 | 부가설명 | SEO 키워드" 형식 (파이프로 구분, 100자 이내)
2. 태그는 한국어 위주 10~15개
3. {season} 계절감이 자연스럽게 녹아들면 좋음
4. 최근 업로드 제목과 겹치지 않게
5. title_sub는 썸네일 상단에 들어갈 짧은 문구 (10자 이내)
6. subtitle_en은 썸네일 하단 영문 (2~3단어)
7. sounds는 아래 [사운드 쿼리 풀] 목록에서 오늘 콘셉트/계절에 맞는 것 3개 선택
   - 반드시 목록에 있는 것만 선택 (임의 생성 금지)
8. video_queries는 아래 [영상 쿼리 풀] 목록에서 오늘 콘셉트/계절/mood에 맞는 것 3~4개 선택
   - 반드시 목록에 있는 것만 선택 (임의 생성 금지)

아래 JSON 형식으로만 응답해. 다른 텍스트 없이 JSON만:
{{
  "title": "...",
  "mood": "...",
  "title_sub": "...",
  "subtitle_en": "...",
  "sounds": ["...", "...", "..."],
  "video_queries": ["...", "...", "...", "..."],
  "tags": ["...", "..."]
}}"""

    # ── Claude API 호출 ───────────────────────────────────────────────
    try:
        client   = anthropic.Anthropic(api_key=api_key)
        message  = client.messages.create(
            model=MODEL,
            max_tokens=768,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = message.content[0].text.strip()
        log.info(f"Claude 응답:\n{raw}")

        # JSON 파싱
        # 혹시 ```json ... ``` 감싸진 경우 제거
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        ai = json.loads(raw.strip())

    except Exception as e:
        log.error(f"Claude API 오류: {e} — 기본 콘셉트로 폴백")
        ai = _fallback_concept(category, season)

    # ── 최종 콘셉트 조합 ─────────────────────────────────────────────
    # AI가 생성한 sounds 사용, 없거나 형식 이상하면 기본값 폴백
    ai_sounds = ai.get("sounds", [])
    if not isinstance(ai_sounds, list) or len(ai_sounds) < 1:
        ai_sounds = sounds
        log.warning("sounds 생성 실패 — 기본 카테고리 쿼리 사용")
    else:
        log.info(f"AI 생성 sounds: {ai_sounds}")

    ai_video_queries = ai.get("video_queries", [])
    if not isinstance(ai_video_queries, list) or len(ai_video_queries) < 1:
        ai_video_queries = None  # None이면 pexels.collect()가 config 기본값 사용
        log.warning("video_queries 생성 실패 — config 기본값 사용")
    else:
        log.info(f"AI 생성 video_queries: {ai_video_queries}")

    concept = {
        "title":        ai.get("title", f"{category_name} | {duration_hours}시간 힐링 사운드"),
        "category":     category,
        "sounds":       ai_sounds,
        "video_queries": ai_video_queries,
        "mood":         ai.get("mood", "calm and relaxing"),
        "duration_hours": duration_hours,
        "title_sub":    ai.get("title_sub", "잠잘때 듣기 좋은"),
        "subtitle_en":  ai.get("subtitle_en", "Healing Music"),
        "tags":         ai.get("tags", [category_name, "ASMR", "힐링음악", "수면음악"]),
        "language":     language,
    }

    log.info(f"생성된 콘셉트: {concept['title']}")
    return concept


def _fallback_concept(category: str, season: str) -> dict:
    """API 실패 시 기본 콘셉트"""
    fallbacks = {
        "rain":        {"title": f"빗소리 ASMR | 1시간 {season} 빗소리 | 수면 집중 힐링",
                        "mood": "cozy rainy", "title_sub": "잠잘때 듣기 좋은",
                        "subtitle_en": "Rain Sounds",
                        "sounds": ["heavy rain", "rain on window", "gentle rain"],
                        "tags": ["빗소리", "ASMR", "수면음악", "힐링음악", "백색소음"]},
        "ocean":       {"title": f"파도 소리 | 1시간 {season} 바다 소리 | 스트레스 해소 힐링",
                        "mood": "peaceful ocean", "title_sub": "마음이 편해지는",
                        "subtitle_en": "Ocean Waves",
                        "sounds": ["ocean waves", "gentle waves", "beach waves"],
                        "tags": ["파도소리", "바다소리", "힐링음악", "수면음악", "ASMR"]},
        "forest":      {"title": f"숲 소리 ASMR | 1시간 {season} 자연 소리 | 명상 힐링",
                        "mood": "peaceful forest", "title_sub": "자연 속에서",
                        "subtitle_en": "Forest Sounds",
                        "sounds": ["forest ambience", "nature sounds", "forest birds"],
                        "tags": ["숲소리", "자연소리", "힐링음악", "명상음악", "ASMR"]},
        "airplane":     {"title": f"비행기 기내 소음 | 1시간 {season} 여행 백색소음 | 수면 집중",
                         "mood": "cozy airplane", "title_sub": "기내에서",
                         "subtitle_en": "Airplane Ambience",
                         "sounds": ["airplane cabin", "aircraft noise", "plane engine"],
                         "tags": ["기내소음", "비행기소음", "백색소음", "수면음악", "ASMR"]},
        "subway":       {"title": f"지하철 소리 | 1시간 {season} 기차 백색소음 | 집중 수면",
                         "mood": "urban travel", "title_sub": "달리는 기차",
                         "subtitle_en": "Train Ambience",
                         "sounds": ["subway train", "metro ambience", "train interior"],
                         "tags": ["지하철소리", "기차소리", "백색소음", "집중음악", "ASMR"]},
        "stream":       {"title": f"계곡 물소리 | 1시간 {season} 자연 힐링 | 명상 수면",
                         "mood": "peaceful stream", "title_sub": "맑은 계곡",
                         "subtitle_en": "Forest Stream",
                         "sounds": ["forest stream", "babbling brook", "mountain stream"],
                         "tags": ["계곡소리", "물소리", "자연소리", "힐링음악", "ASMR"]},
        "summer_night": {"title": f"여름밤 귀뚜라미 | 1시간 {season} 밤 자연소리 | 숙면 힐링",
                         "mood": "warm summer night", "title_sub": "여름밤에",
                         "subtitle_en": "Summer Night",
                         "sounds": ["crickets night", "summer insects", "night nature"],
                         "tags": ["귀뚜라미소리", "여름밤", "자연소리", "수면음악", "ASMR"]},
        "winter_snow":  {"title": f"겨울 눈 내리는 소리 | 1시간 {season} 설경 힐링 | 수면",
                         "mood": "silent winter", "title_sub": "눈 내리는 밤",
                         "subtitle_en": "Winter Snow",
                         "sounds": ["winter ambience", "snow wind", "winter forest"],
                         "tags": ["눈소리", "겨울소리", "백색소음", "수면음악", "ASMR"]},
        "summer_rain": {"title": f"여름 소나기 나뭇잎 소리 | 1시간 {season} 빗소리 ASMR | 힐링",
                        "mood": "warm summer rain", "title_sub": "여름 소나기",
                        "subtitle_en": "Summer Rain",
                        "sounds": ["summer rain", "rain leaves", "rain garden"],
                        "tags": ["여름소나기", "빗소리", "나뭇잎빗소리", "자연소리", "ASMR"]},
        "snow_walk":  {"title": f"눈밭 발자국 소리 | 1시간 {season} 겨울 ASMR | 뽀득뽀득",
                        "mood": "peaceful winter walk", "title_sub": "뽀득뽀득",
                        "subtitle_en": "Snow Walk ASMR",
                        "sounds": ["snow footsteps", "crunching snow", "snow steps"],
                        "tags": ["눈발자국", "눈ASMR", "겨울소리", "뽀득뽀득", "ASMR"]},
    }
    fb = fallbacks.get(category, fallbacks["rain"])
    return fb