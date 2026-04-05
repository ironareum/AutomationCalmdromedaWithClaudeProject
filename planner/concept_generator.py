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
2026.04.04 feat: 3레이어 사운드 구조 (main/sub/point) + 볼륨 랜덤화 + calm 쿼리 강화
2026.04.04 feat: 제목 SEO 키워드 강화, 태그 한/영 통합, 폴백 개선
2026.04.05 fix: rain/forest 하이노이즈 제거, white_noise brown noise만 허용
2026.04.05 feat: 신규 카테고리 5개 추가 (cave_water/ice_melt/bath_house/train_ride/temple_bell)
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

# 공통 고정 태그 (모든 영상에 포함)
COMMON_TAGS = [
    # 채널 브랜딩
    "Calmdromeda", "캄드로메다",
    # 힐링/수면 한국어
    "힐링음악", "수면음악", "명상", "백색소음", "자연소리",
    "수면유도", "숙면사운드", "불면증", "잠안올때", "잠오는음악",
    "편안한음악", "앰비언트", "릴렉스", "마음이편안해지는",
    "밤에듣는음악", "잘때듣기좋은노래", "공부음악",
    # 힐링/수면 영문
    "asmr", "asmr sounds", "healing", "healing music", "healing sounds",
    "meditation", "sleep Music", "deep sleep", "relax", "relaxing sounds",
    "Inner Peace", "ambient", "white noise", "nature sounds",
    "stress relief", "sleep sound",
]

# 카테고리별 추가 태그
CATEGORY_TAGS = {
    "rain":          ["빗소리", "빗소리ASMR", "rain sounds", "rain asmr"],
    "rain_thunder":  ["빗소리", "천둥소리", "thunder", "storm sounds"],
    "ocean":         ["파도소리", "바다소리", "ocean sounds", "wave sound"],
    "forest":        ["숲소리", "자연소리", "forest sounds", "nature asmr"],
    "birds":         ["새소리", "풀벌레소리", "bird sounds", "morning birds"],
    "white_noise":   ["백색소음", "집중사운드", "white noise", "focus sounds"],
    "cafe":          ["카페소리", "카페음악", "cafe sounds", "coffee shop"],
    "camping":       ["캠핑소리", "모닥불소리", "campfire", "camping sounds"],
    "airplane":      ["비행기소리", "기내소음", "airplane sounds", "flight asmr"],
    "subway":        ["지하철소리", "기차소리", "train sounds", "subway asmr"],
    "library":       ["도서관소리", "독서실소음", "library sounds", "study asmr"],
    "underwater":    ["수중소리", "바닷속소리", "underwater sounds", "aquarium"],
    "hot_spring":    ["온천소리", "물소리", "water sounds", "hot spring"],
    "fireplace_rain":["모닥불빗소리", "벽난로소리", "fireplace rain", "cozy sounds"],
    "summer_night":  ["여름밤소리", "귀뚜라미소리", "summer night", "cricket sounds"],
    "winter_snow":   ["눈소리", "겨울소리", "snow sounds", "winter asmr"],
    "study_room":    ["공부소리", "집중사운드", "study sounds", "focus asmr"],
    "stream":        ["계곡소리", "시냇물소리", "stream sounds", "river asmr"],
    "summer_rain":   ["여름빗소리", "소나기소리", "summer rain", "rain leaves"],
    "snow_walk":     ["눈밭소리", "발자국소리", "snow walking", "winter walk"],
}

# 카테고리별 제목 첫 키워드 (사람들이 실제로 검색하는 단어)
CATEGORY_TITLE_KEYWORDS = {
    "rain":           "빗소리 ASMR",
    "rain_thunder":   "천둥 빗소리 ASMR",
    "ocean":          "파도소리 ASMR",
    "forest":         "숲속 소리 ASMR",
    "birds":          "새소리 ASMR",
    "white_noise":    "백색소음",
    "cafe":           "카페 소리 ASMR",
    "camping":        "모닥불 소리 ASMR",
    "airplane":       "비행기 소리 ASMR",
    "subway":         "지하철 소리 ASMR",
    "library":        "도서관 소리 ASMR",
    "underwater":     "수중 소리 ASMR",
    "hot_spring":     "온천 물소리 ASMR",
    "fireplace_rain": "모닥불 빗소리 ASMR",
    "summer_night":   "여름밤 귀뚜라미 ASMR",
    "winter_snow":    "겨울 눈소리 ASMR",
    "study_room":     "공부 집중 소리 ASMR",
    "stream":         "계곡 물소리 ASMR",
    "summer_rain":    "여름 빗소리 ASMR",
    "snow_walk":      "눈밭 발자국 ASMR",
}

# 지원 카테고리 전체 목록
ALL_CATEGORIES = [
    "rain", "rain_thunder", "ocean", "forest", "birds",
    "white_noise", "cafe", "camping",
    "airplane", "subway", "library", "underwater",
    "hot_spring", "fireplace_rain", "summer_night",
    "winter_snow", "study_room", "stream",
    "summer_rain", "snow_walk",
    "cave_water", "ice_melt", "bath_house", "train_ride", "temple_bell",
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
    "water_drip_group": ["cave_water", "ice_melt"],
    "zen_group":     ["temple_bell", "bath_house"],
    "transit_group": ["airplane", "subway", "train_ride"],
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
    "cave_water":     "동굴 물방울 소리",
    "ice_melt":       "얼음 녹는 소리",
    "bath_house":     "대중목욕탕/온천 ASMR",
    "train_ride":     "열차 실내 소리",
    "temple_bell":    "목탁/사찰 소리",
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
    "cave_water":     ["cave waterfall", "stalactite cave", "underground cave water",
                       "cave dripping", "dark cave nature"],
    "ice_melt":       ["ice melting water", "ice close up", "frozen water melting",
                       "crystal ice water", "cold water drops"],
    "bath_house":     ["hot spring pool", "steam bath water", "spa water surface",
                       "thermal pool steam", "onsen japan"],
    "train_ride":     ["train window night", "train interior moving", "railway journey",
                       "train window landscape", "night train window"],
    "temple_bell":    ["zen temple garden", "buddhist temple", "japanese garden calm",
                       "temple morning", "buddhist meditation"],
}

# 카테고리별 검증된 Freesound 쿼리 풀
# AI는 이 목록 안에서만 3개 선택 → 엉뚱한 키워드 방지
# 카테고리별 검증된 Freesound 쿼리 풀
# 구조: {"main": [...], "sub": [...], "point": [...]}
# main  = 앰비언스 핵심음 (60~80%)
# sub   = 배경 보완음 (10~30%)
# point = 거의 안 들리는 포인트음 (5~15%)
CATEGORY_SOUNDS = {
    "rain": {
        "main":  ["gentle rain loopable", "soft rain nature calm", "rain window indoor calm"],
        "sub":   ["rain roof gentle", "light rain drizzle ambient"],
        "point": ["rain drops soft single", "rain puddle gentle"],
    },
    "rain_thunder": {
        "main":  ["thunderstorm rain ambient", "heavy rain thunder calm"],
        "sub":   ["storm rain background", "rain ambient loop"],
        "point": ["distant thunder low", "thunder rumble far"],
    },
    "ocean": {
        "main":  ["gentle ocean waves ambient", "calm sea waves loop", "soft ocean shore"],
        "sub":   ["coastal breeze soft", "ocean wind gentle"],
        "point": ["distant seagulls calm", "water lapping soft"],
    },
    "forest": {
        "main":  ["forest ambience calm", "deep forest quiet ambient", "woodland morning calm"],
        "sub":   ["leaves rustle gentle", "forest background quiet"],
        "point": ["birds chirping distant soft", "forest insects quiet low"],
    },
    "birds": {
        "main":  ["birds chirping morning calm", "birdsong peaceful ambient", "dawn chorus gentle"],
        "sub":   ["forest background quiet", "nature ambience soft"],
        "point": ["single bird distant", "wind leaves gentle"],
    },
    "white_noise": {
        "main":  ["brown noise smooth", "brown noise sleep ambient", "deep brown noise calm"],
        "sub":   ["room tone soft ambient", "fan noise soft low"],
        "point": ["ambient hum quiet", "low frequency hum gentle"],
    },
    "cafe": {
        "main":  ["cafe ambience calm", "coffee shop background quiet", "indoor cafe soft"],
        "sub":   ["cafe background murmur gentle", "indoor ambience soft"],
        "point": ["coffee cup gentle", "cafe distant chatter low"],
    },
    "camping": {
        "main":  ["campfire crackling calm", "fire crackling gentle loop"],
        "sub":   ["night forest ambient quiet", "outdoor night calm"],
        "point": ["crickets distant night", "wind trees gentle"],
    },
    "airplane": {
        "main":  ["airplane cabin ambient", "aircraft interior noise calm", "inflight ambience loop"],
        "sub":   ["plane engine hum gentle", "airplane interior background"],
        "point": ["cabin air circulation soft", "flight ambient low"],
    },
    "subway": {
        "main":  ["subway train interior calm", "metro train ride ambient", "underground train gentle"],
        "sub":   ["rail vibration ambient", "train rumble soft"],
        "point": ["station distant ambient", "train door soft"],
    },
    "library": {
        "main":  ["library ambience quiet", "reading room ambient calm", "study room quiet"],
        "sub":   ["pencil writing soft", "paper writing gentle ambient"],
        "point": ["page turn soft single", "library distant footsteps"],
    },
    "underwater": {
        "main":  ["underwater ambience calm", "aquarium ambient gentle", "deep ocean ambient quiet"],
        "sub":   ["water bubbles soft gentle", "underwater current soft"],
        "point": ["deep sea ambient low", "water flow distant gentle"],
    },
    "hot_spring": {
        "main":  ["water flowing calm gentle", "stream flowing peaceful", "hot spring ambient"],
        "sub":   ["steam ambient soft", "water bubbling gentle"],
        "point": ["nature birds distant", "wind soft nature"],
    },
    "fireplace_rain": {
        "main":  ["fireplace crackling calm", "fire indoor ambient gentle"],
        "sub":   ["rain window soft background", "indoor rain ambient gentle"],
        "point": ["wood fire crackle soft", "rain drizzle distant"],
    },
    "summer_night": {
        "main":  ["crickets night ambient calm", "summer night insects gentle"],
        "sub":   ["night nature ambient soft", "evening insects background"],
        "point": ["distant frog night", "night breeze soft"],
    },
    "winter_snow": {
        "main":  ["winter ambience calm quiet", "snow falling ambient gentle"],
        "sub":   ["soft winter wind low", "cold wind nature quiet"],
        "point": ["snow footsteps crunch soft", "winter forest distant"],
    },
    "study_room": {
        "main":  ["quiet room ambient calm", "study ambience soft", "indoor quiet ambient"],
        "sub":   ["clock ticking gentle soft", "air conditioning soft hum"],
        "point": ["pencil writing paper soft", "keyboard typing gentle"],
    },
    "stream": {
        "main":  ["forest stream gentle calm", "babbling brook peaceful", "creek water flowing soft"],
        "sub":   ["nature ambient stream background", "river gentle flow"],
        "point": ["birds stream distant", "wind leaves stream"],
    },
    "summer_rain": {
        "main":  ["summer rain leaves calm", "rain garden gentle ambient", "tropical rain soft"],
        "sub":   ["rain grass soft background", "summer shower gentle"],
        "point": ["rain drops leaves soft", "summer breeze gentle"],
    },
    "snow_walk": {
        "main":  ["snow walking ambient calm", "winter footsteps snow gentle"],
        "sub":   ["winter forest ambient quiet", "cold wind soft nature"],
        "point": ["snow crunch soft single", "winter silence ambient"],
    },
    "cave_water": {
        "main":  ["cave dripping water ambient", "cave water drops echo", "underground cave ambient"],
        "sub":   ["cave echo soft", "water drip cave gentle"],
        "point": ["cave ambient low hum", "distant water drip"],
    },
    "ice_melt": {
        "main":  ["ice melting water gentle", "water drips ice calm", "cold water drops ambient"],
        "sub":   ["ice cracking soft gentle", "water trickle soft"],
        "point": ["ice ambient quiet", "frozen water ambient"],
    },
    "bath_house": {
        "main":  ["onsen hot spring ambient", "bath water gentle splash", "spa pool ambient calm"],
        "sub":   ["steam ambient soft", "water surface gentle"],
        "point": ["distant bath ambient", "water bubbles soft low"],
    },
    "train_ride": {
        "main":  ["train interior ambient calm", "railway ride ambient", "train window moving gentle"],
        "sub":   ["train rhythm gentle", "rail track ambient soft"],
        "point": ["train distant whistle soft", "cabin ambient quiet"],
    },
    "temple_bell": {
        "main":  ["temple bell ambient calm", "buddhist bell meditation", "zen bell gentle"],
        "sub":   ["birds temple morning soft", "nature temple ambient"],
        "point": ["distant temple bell", "wind chime gentle soft"],
    },
}

# 카테고리별 사운드 특성 힌트 (프롬프트에 주입 → AI가 카테고리 특성 정확히 인식)
CATEGORY_SOUND_HINTS = {
    "rain":          "차분하고 부드러운 빗소리. 강한 바람/하이 프리퀀시 절대 금지. 창문에 조용히 떨어지는 빗소리 느낌.",
    "rain_thunder":  "빗소리+천둥. 극적이고 웅장한 폭풍우 느낌.",
    "ocean":         "파도 소리. 해변에서 듣는 파도/바다 느낌.",
    "forest":        "조용하고 차분한 숲 앰비언스. 강한 바람/하이 노이즈 절대 금지. 나뭇잎 살랑이는 소리+풀벌레+먼 새소리. 고요한 숲 공간감.",
    "birds":         "새소리가 메인. 특정 새 울음소리+아침 합창. 숲 배경음 최소화. 새 울음이 전면에.",
    "white_noise":   "브라운 노이즈만 허용. 화이트/핑크 노이즈 절대 금지. 저음 위주의 부드럽고 묵직한 소리. 아주 작은 볼륨으로.",
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
    "cave_water":    "동굴 물방울. 천천히 떨어지는 물방울+동굴 에코. 고요하고 신비로운 느낌. 심플하게.",
    "ice_melt":      "얼음 녹는 소리. 물방울 떨어지는 소리+얼음 녹는 소리. 조용하고 차갑고 투명한 느낌.",
    "bath_house":    "대중목욕탕/온천. 잔잔한 물소리+증기+멀리서 들리는 물소리. 따뜻하고 포근한 느낌.",
    "train_ride":    "열차 실내. 리드미컬한 레일 소리+기차 진동. 잠들 것 같은 부드러운 기차 주행음. 자연음 절대 금지.",
    "temple_bell":   "목탁/사찰. 차분한 목탁 소리+잔잔한 새소리. 저음 목탁, 하이 프리퀀시 금지. 명상적이고 고요한 느낌.",
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
    # 메인/서브/포인트 구조에서 각 레이어 쿼리 추출
    cat_sounds = CATEGORY_SOUNDS.get(category, {})
    sounds_main  = cat_sounds.get("main",  ["nature ambient calm"])
    sounds_sub   = cat_sounds.get("sub",   sounds_main[:1])   # 폴백: main에서 가져옴
    sounds_point = cat_sounds.get("point", sounds_main[:1])   # 폴백: main에서 가져옴
    sounds_all   = sounds_main + sounds_sub + sounds_point

    log.info(f"AI 기획 시작 — 카테고리: {category}({category_name}), 계절: {season}")

    # ── 프롬프트 ──────────────────────────────────────────────────────
    recent_titles_str = "\n".join(f"- {t}" for t in recent_titles[:10]) or "없음"

    # 프롬프트용 사운드 풀 (메인/서브/포인트 구분해서 전달)
    default_sounds_str = (
        f"[메인 앰비언스] {', '.join(sounds_main)}\n"
        f"[서브 배경음]   {', '.join(sounds_sub)}\n"
        f"[포인트 효과음] {', '.join(sounds_point)}"
    )
    default_videos = CATEGORY_VIDEO_QUERIES.get(category, [category])
    default_videos_str = ", ".join(default_videos)
    sound_hint = CATEGORY_SOUND_HINTS.get(category, "카테고리에 맞는 자연음 선택")
    title_keyword = CATEGORY_TITLE_KEYWORDS.get(category, f"{category_name} ASMR")
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
1. 제목은 "{title_keyword} | 부가설명 | SEO 키워드" 형식 (파이프로 구분, 100자 이내)
   - 반드시 "{title_keyword}"로 시작 — 사람들이 실제 검색하는 단어가 앞에 와야 함
   - 예: "{title_keyword} | 1시간 깊은 숙면 & 명상 | 공부할 때 듣기 좋은"
2. 태그는 한국어 위주 10~15개
3. 제목에 봄/여름/가을/겨울 계절 키워드 사용 금지 — 계절과 무관하게 언제든 시청 가능한 제목
4. 최근 업로드 제목과 겹치지 않게
5. title_sub는 썸네일 상단에 들어갈 짧은 문구 (10자 이내)
6. subtitle_en은 썸네일 하단 영문 (2~3단어)
7. sounds는 반드시 아래 3개 구조로 선택:
   - sounds[0]: [메인 앰비언스] 목록에서 1개 선택 (핵심 공간음)
   - sounds[1]: [서브 배경음] 목록에서 1개 선택 (보완 배경음)
   - sounds[2]: [포인트 효과음] 목록에서 1개 선택 (거의 안 들리는 세부음)
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
    if not isinstance(ai_sounds, list) or len(ai_sounds) < 3:
        ai_sounds = [sounds_main[0], sounds_sub[0], sounds_point[0]]
        log.warning("sounds 생성 실패 — 기본 메인/서브/포인트 쿼리 사용")
    else:
        log.info(f"AI 생성 sounds: {ai_sounds}")

    ai_video_queries = ai.get("video_queries", [])
    if not isinstance(ai_video_queries, list) or len(ai_video_queries) < 1:
        ai_video_queries = None  # None이면 pexels.collect()가 config 기본값 사용
        log.warning("video_queries 생성 실패 — config 기본값 사용")
    else:
        log.info(f"AI 생성 video_queries: {ai_video_queries}")

    # 태그: AI 생성 태그 + 카테고리별 태그 + 공통 태그 조합 (중복 제거)
    ai_tags = ai.get("tags", [])
    cat_tags = CATEGORY_TAGS.get(category, [])
    merged_tags = list(dict.fromkeys(ai_tags + cat_tags + COMMON_TAGS))[:50]

    concept = {
        "title":        ai.get("title", f"{category_name} | {duration_hours}시간 힐링 사운드"),
        "category":     category,
        "sounds":       ai_sounds,
        "sound_layers": {
            "main":  cat_sounds.get("main",  [ai_sounds[0]] if ai_sounds else ["nature ambient calm"]),
            "sub":   cat_sounds.get("sub",   [ai_sounds[1]] if len(ai_sounds) > 1 else ["wind gentle soft"]),
            "point": cat_sounds.get("point", [ai_sounds[2]] if len(ai_sounds) > 2 else ["birds distant quiet"]),
        },
        "video_queries": ai_video_queries,
        "mood":         ai.get("mood", "calm and relaxing"),
        "duration_hours": duration_hours,
        "title_sub":    ai.get("title_sub", "잠잘때 듣기 좋은"),
        "subtitle_en":  ai.get("subtitle_en", "Healing Music"),
        "tags":         merged_tags,
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
    cat_sounds = CATEGORY_SOUNDS.get(category, {})
    sounds = [
        cat_sounds.get("main",  ["nature ambient calm"])[0],
        cat_sounds.get("sub",   ["wind gentle soft"])[0],
        cat_sounds.get("point", ["birds distant quiet"])[0],
    ]
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