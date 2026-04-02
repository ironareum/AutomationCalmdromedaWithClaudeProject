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
2026.04.01 fix: 사운드 타겟팅 강화, 영상 재사용 모드 추가, 그룹 기반 카테고리 로테이션
2026.04.01 feat: forest/birds 차별화, 콘셉트 다양성 강화, 최근 제목 10개 참조
2026.04.02 fix: 계절 키워드 제거, 프롬프트 수정


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

# 비슷한 카테고리 그룹 — 같은 그룹 연속 방지
CATEGORY_GROUPS = {
    "rain_group":    ["rain", "rain_thunder", "summer_rain", "fireplace_rain"],
    "nature_group":  ["forest", "birds", "stream", "summer_night"],
    "water_group":   ["ocean", "underwater", "hot_spring"],
    "indoor_group":  ["cafe", "library", "study_room"],
    "travel_group":  ["airplane", "subway"],
    "ambient_group": ["white_noise", "camping"],
    "winter_group":  ["winter_snow", "snow_walk"],
}

def _get_group(category: str) -> str | None:
    """카테고리가 속한 그룹 반환"""
    for group, cats in CATEGORY_GROUPS.items():
        if category in cats:
            return group
    return None


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
    "underwater":   "수족관/바닷속 물 소리",
    "hot_spring":   "온천/물소리",
    "fireplace_rain": "모닥불+빗소리",
    "summer_night": "여름밤 귀뚜라미",
    "winter_snow":  "겨울 눈 내리는 소리",
    "study_room":   "공부방 분위기",
    "stream":         "계곡/시냇물",
    "summer_rain":    "여름 소나기/나뭇잎 빗소리",
    "snow_walk":      "눈밭 발자국 소리",
}

# 카테고리별 Freesound 검색 쿼리
# 카테고리별 기본 영상 쿼리 (Claude 프롬프트 힌트용)
CATEGORY_VIDEO_QUERIES = {
    "rain": [
        "rain window", "rainy day", "rain drops glass",
        "rain street", "rain nature", "rain city"
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
    "camping":        ["campfire night", "tent camping", "forest night",
                       "campfire outdoor", "starry night camping", "bonfire nature"],
    "airplane":       ["airplane window clouds", "plane window sky", "aircraft clouds",
                       "flying above clouds", "airplane interior"],
    "subway":         ["subway train", "metro train window", "train journey",
                       "underground metro", "train window night"],
    "library":        ["library interior", "books shelf", "reading room",
                       "quiet study room", "library light"],
    "underwater":     ["underwater ocean", "aquarium fish", "coral reef",
                       "deep sea", "ocean underwater"],
    "hot_spring":     ["hot spring water", "waterfall nature", "steam water",
                       "thermal bath", "water flowing rocks"],
    "fireplace_rain": ["fireplace cozy", "fireplace rain window", "indoor fire",
                       "cozy cabin fireplace", "fire warm indoor"],
    "summer_night":   ["summer night nature", "fireflies night", "night meadow",
                       "sunset field", "dusk nature"],
    "winter_snow":    ["snowfall nature", "winter forest snow", "snow falling",
                       "winter landscape", "snowy forest"],
    "study_room":     ["desk lamp night", "study room cozy", "reading lamp",
                       "quiet room interior", "night study"],
    "stream":         ["forest stream", "mountain creek", "river stones",
                       "babbling brook", "waterfall forest"],
    "summer_rain":    ["summer rain leaves", "rain garden plants", "tropical rain",
                       "rain drops leaves", "rain forest summer"],
    "snow_walk":      ["snow walking path", "winter snow walk", "snowy forest path",
                       "footprints snow", "winter walk nature"],
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
    "camping":        ["campfire", "forest night", "crickets night",
                       "campfire crackling", "night forest", "fire crackling outdoor"],
    "airplane":       ["airplane cabin", "aircraft noise", "plane engine", "airplane ambience",
                       "flight noise", "jet engine distant"],
    "subway":         ["subway train", "metro ambience", "train interior", "train noise",
                       "underground train", "train rumble"],
    "library":        ["library ambience", "quiet room", "pages turning", "indoor quiet",
                       "study ambience", "soft indoor"],
    "underwater":     ["underwater ambience", "aquarium sounds", "deep ocean", "water bubbles",
                       "underwater bubbles", "ocean depth"],
    "hot_spring":     ["hot spring", "water flowing", "steam water", "waterfall gentle",
                       "flowing water", "water stream relaxing"],
    "fireplace_rain": ["fireplace crackling", "fire rain", "campfire rain", "crackling fire",
                       "fireplace indoor", "wood fire crackling"],
    "summer_night":   ["crickets night", "summer insects", "night nature", "evening insects",
                       "cicada summer", "summer night ambient"],
    "winter_snow":    ["winter ambience", "snow wind", "blizzard", "winter forest",
                       "cold wind nature", "snowfall silent"],
    "study_room":     ["quiet room", "study ambience", "clock ticking", "indoor quiet study",
                       "library quiet", "focus ambience"],
    "stream":         ["forest stream", "babbling brook", "mountain stream", "creek water",
                       "river flowing", "stream nature"],
    "summer_rain":    ["summer rain", "rain leaves", "tropical rain", "rain garden",
                       "summer shower", "rain grass"],
    "snow_walk":      ["snow footsteps", "snow walking", "crunching snow", "snow steps",
                       "winter footsteps", "snow crunch outdoor"],
}

# 카테고리별 사운드 특성 힌트 (프롬프트에 주입 → AI가 카테고리 특성 정확히 인식)
CATEGORY_SOUND_HINTS = {
    "rain":          "빗소리 위주. 실내에서 듣는 빗소리 느낌.",
    "rain_thunder":  "빗소리+천둥. 극적이고 웅장한 폭풍우 느낌.",
    "ocean":         "파도 소리. 해변에서 듣는 파도/바다 느낌.",
    "forest":        "숲 앰비언스. 바람+나뭇잎+풀벌레 위주. 새소리는 배경으로만. 숲 전체 공간감.",
    "birds":         "새소리가 메인. 특정 새 울음소리+아침 합창. 숲 배경음 최소화. 새 울음이 전면에.",
    "white_noise":   "백색소음. 지속적이고 일정한 노이즈.",
    "cafe":          "카페 실내음. 대화소리+커피머신+배경음악 없는 분위기.",
    "camping":       "캠핑. 모닥불 타는 소리+밤 자연음.",
    "airplane":      "비행기 기내. 엔진소음+기내 공기소리. 파도/새소리 절대 금지.",
    "subway":        "지하철/기차 주행음. 철로 소리+진동음. 자연음 절대 금지.",
    "library":       "도서관 실내. 조용한 환경+책 넘기는 소리+먼 발소리.",
    "underwater":    "수중/바닷속. 물속 기포+수압음+수중 특유의 울림. 파도/해변 소리 절대 금지.",
    "hot_spring":    "온천/물소리. 물 흐르는 소리+증기+자연.",
    "fireplace_rain":"모닥불+빗소리. 실내 따뜻한 불+창밖 비.",
    "summer_night":  "여름밤. 귀뚜라미+매미+밤 곤충소리.",
    "winter_snow":   "겨울 설경. 눈 밟는 소리+차가운 바람+고요함.",
    "study_room":    "공부방. 조용한 실내+시계소리+에어컨 소음.",
    "stream":        "계곡/시냇물. 물 흐르는 소리+돌 위 물소리.",
    "summer_rain":   "여름 소나기. 나뭇잎에 떨어지는 빗소리+흙냄새 느낌.",
    "snow_walk":     "눈밭 발자국. 뽀득뽀득 눈 밟는 소리 위주.",
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
    카테고리 선택 로직 (그룹 기반 반복 방지)

    1. 미사용 카테고리 중 → 최근 사용 그룹 제외 후 랜덤
    2. 미사용 없으면 → 최근 3개 그룹 제외 후 랜덤
    3. 그래도 없으면 → 최근 3개 카테고리만 피하고 랜덤

    [그룹 반복 방지]
    rain_group: rain, rain_thunder, summer_rain, fireplace_rain
    → 이 중 하나 나왔으면 다음엔 다른 그룹에서 선택
    """
    # 최근 사용 그룹 파악 (최근 4개)
    recent_groups = []
    for cat in recent_categories[:4]:
        g = _get_group(cat)
        if g and g not in recent_groups:
            recent_groups.append(g)

    # 1단계: 미사용 카테고리 중 최근 그룹 제외
    unused = [c for c in ALL_CATEGORIES if c not in recent_categories]
    if unused:
        # 최근 그룹 제외한 미사용 카테고리
        preferred = [c for c in unused if _get_group(c) not in recent_groups]
        pool = preferred if preferred else unused
        chosen = random.choice(pool)
        reason = f"미사용 {len(unused)}개 중" + (f" 최근 그룹({recent_groups[:2]}) 제외" if preferred != unused else "")
        log.info(f"카테고리 선택: {chosen} ({reason} 랜덤)")
        return chosen

    # 2단계: 전부 최근에 썼으면 최근 3개 그룹 제외
    available = [c for c in ALL_CATEGORIES
                 if c not in recent_categories[:3]
                 and _get_group(c) not in recent_groups[:3]]
    if available:
        chosen = random.choice(available)
        log.info(f"카테고리 선택: {chosen} (전체 로테이션 완료, 그룹 제외 랜덤)")
        return chosen

    # 3단계: 최후 수단 — 최근 3개만 피함
    fallback = [c for c in ALL_CATEGORIES if c not in recent_categories[:3]]
    chosen = random.choice(fallback) if fallback else random.choice(ALL_CATEGORIES)
    log.info(f"카테고리 선택: {chosen} (최후 수단 랜덤)")
    return chosen


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
    recent_titles_str = "\n".join(f"- {t}" for t in recent_titles[:10]) or "없음"

    default_sounds_str = ", ".join(sounds)
    default_videos = CATEGORY_VIDEO_QUERIES.get(category, [category])
    default_videos_str = ", ".join(default_videos)
    sound_hint = CATEGORY_SOUND_HINTS.get(category, "카테고리에 맞는 자연음 선택")
    prompt = f"""너는 한국 유튜브 힐링/ASMR 채널 'Calmdromeda'의 콘텐츠 기획자야.
오늘 업로드할 자연 사운드 영상의 콘셉트를 만들어줘.

[오늘 정보]
- 날짜: {today.strftime("%Y년 %m월 %d일")}
- 선택된 카테고리: {category_name}
- 영상 길이: {duration_hours}시간

[최근 업로드 제목 (겹치면 안 됨)]
{recent_titles_str}

[카테고리 사운드 특성 — 반드시 준수]
{sound_hint}

[사운드 쿼리 풀 — 이 중에서만 3개 선택]
{default_sounds_str}

[영상 쿼리 풀 — 이 중에서만 3~4개 선택]
{default_videos_str}

[요구사항]
1. 제목은 "메인 키워드 | 부가설명 | SEO 키워드" 형식 (파이프로 구분, 100자 이내)
2. 태그는 한국어 위주 10~15개
3. 제목에 봄/여름/가을/겨울 계절 키워드 사용 금지 — 계절과 무관하게 언제든 시청 가능한 제목
4. 최근 업로드 제목과 겹치지 않게
5. title_sub는 썸네일 상단에 들어갈 짧은 문구 (10자 이내)
6. subtitle_en은 썸네일 하단 영문 (2~3단어)
7. sounds는 [사운드 쿼리 풀] 목록에서 [카테고리 사운드 특성]에 맞는 것 3개 선택
   - 반드시 목록에 있는 것만 선택 (임의 생성 금지)
   - 카테고리 특성에 어긋나는 쿼리 절대 선택 금지
8. video_queries는 [영상 쿼리 풀] 목록에서 오늘 콘셉트/계절/mood에 맞는 것 3~4개 선택
   - 반드시 목록에 있는 것만 선택 (임의 생성 금지)
9. 제목/콘셉트는 최근 업로드 제목과 뚜렷이 달라야 함
   - 같은 카테고리라도 시간대/장소/분위기가 확실히 다른 각도로 접근
   - 예: 빗소리라도 "창밖 빗소리", "한여름 소나기", "가을 비", "새벽 이슬비", "도심 빗소리", "깊은 밤 빗소리", "양철지붕 빗소리" 등 차별화
   - 제목만 다르고 실제 콘셉트가 같으면 안 됨

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
    """
    API 실패 시 기본 콘셉트 자동 생성
    CATEGORY_KO, CATEGORY_SOUNDS, CATEGORY_VIDEO_QUERIES 기반으로
    모든 카테고리를 자동 지원 → 새 카테고리 추가해도 자동 적용
    """
    category_name = CATEGORY_KO.get(category, category)
    sounds        = CATEGORY_SOUNDS.get(category, ["nature sounds"])[:3]
    video_queries = CATEGORY_VIDEO_QUERIES.get(category, [category])[:3]

    return {
        "title":      f"{category_name} ASMR | 1시간 {category_name} | 수면 집중 힐링",
        "mood":       f"calm and relaxing {category_name}",
        "title_sub":  "힐링 사운드",
        "subtitle_en": " ".join(w.capitalize() for w in category.split("_")[:2]),
        "sounds":     sounds,
        "video_queries": video_queries,
        "tags":       [category_name, "ASMR", "수면음악", "힐링음악", "백색소음", "명상음악"],
    }