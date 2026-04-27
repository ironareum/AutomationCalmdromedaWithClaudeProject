# ============================================================
#  config.py  —  파이프라인 설정(Configuration for calmdromeda pipeline)
# ============================================================
#  API 키는 .env 파일에 저장하세요 (git에 올라가지 않음)
#  .env.example 참고
#
# ============================================================
"""
# Homebrew 설치
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    설치 후 반드시 셋팅
    ==> Next steps:
    - Run these commands in your terminal to add Homebrew to your PATH:
        echo >> /Users/areumkang/.zprofile
        echo 'eval "$(/opt/homebrew/bin/brew shellenv zsh)"' >> /Users/areumkang/.zprofile
        eval "$(/opt/homebrew/bin/brew shellenv zsh)"

1. 파이썬 버전 설정 : 3.1.0 (3.1.20 설치됨)
1) 파이썬 버전 업그레이드
    brew install python@3.10
    brew info python@3.10 # 설치경로 확인

2) 가상환경 다시 생성
    /opt/homebrew/opt/python@3.10/bin/python3.10 -m venv .venv # 무조건 3.10으로 강제생성
    source .venv/bin/activate # 가상환경 활성화
    /Users/areumkang/PycharmProjects/AutomationCalmdromedaWithClaudeProject/.venv/bin/python # 프로젝트 내 파이썬 버전 확인

    # 가상환경 삭제(파이썬 버전 잘못 만들었을경우 수행)
    rm -rf .venv
    python3.10 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

2. requirements 설치
    pip install -r requirements.txt

3. FFmpeg 설치
    brew install ffmpeg

    설치 후 확인
    which ffmpeg ( /opt/homebrew/bin/ffmpeg 나오면 정상)
    ffmpeg -version :

============================================================
2026.03.30 신규 신규 카테고리 추가(12개)

============================================================
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    # API Keys (set in .env file)
    freesound_api_key: str = os.getenv("FREESOUND_API_KEY", "")
    pexels_api_key: str = os.getenv("PEXELS_API_KEY", "")
    youtube_client_secret_path: str = os.getenv("YOUTUBE_CLIENT_SECRET", "credentials/client_secret.json")
    claude_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")  # Phase 2에서 사용

    # Paths
    base_dir: Path = Path(__file__).parent
    output_dir: Path = base_dir / "output"
    assets_dir: Path = base_dir / "assets"
    thumbnails_dir: Path = base_dir / "assets" / "thumbnail_backgrounds"

    # Video Settings
    video_resolution: tuple = (1920, 1080)  # 1080p
    video_fps: int = 30
    default_duration_hours: int = 3

    # FFmpeg
    ffmpeg_threads: int = 4
    video_bitrate: str = "2000k"
    audio_bitrate: str = "192k"

    # Thumbnail
    thumbnail_size: tuple = (1280, 720)
    thumbnail_font_size: int = 52

    # Upload 설정
    upload_enabled: bool = os.getenv("UPLOAD_ENABLED", "true").lower() == "true"
    upload_hour_kst: int = int(os.getenv("UPLOAD_HOUR_KST", "18"))    # 오후 6시 KST
    upload_minute_kst: int = int(os.getenv("UPLOAD_MINUTE_KST", "30"))  # 30분
    youtube_token_path: str = os.getenv("YOUTUBE_TOKEN", "credentials/token.json")

    # [미사용] Instagram 설정
    # instagram_enabled: bool = os.getenv("INSTAGRAM_ENABLED", "true").lower() == "true"
    # instagram_access_token: str = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    # instagram_user_id: str = os.getenv("INSTAGRAM_USER_ID", "")

    # Category → Pexels search query mapping
    category_queries = {
        "rain": ["rain window", "rainy day", "rain drops glass", "storm rain",
                 "heavy rain nature", "rain street", "rain forest", "raining outside",
                 "rain puddle", "rain roof", "rain night", "rainfall"],
        "rain_thunder":  ["thunderstorm", "dark storm", "lightning rain", "rainy night"],
        "ocean":         ["ocean waves", "beach waves", "sea waves night", "calm ocean"],
        "forest":        ["forest nature", "misty forest", "green forest", "forest morning"],
        "birds":         ["birds nature", "morning forest", "peaceful garden", "bird wildlife"],
        "white_noise":   ["abstract calm", "minimalist nature", "soft light nature", "peaceful landscape"],
        "cafe":          ["cafe interior table", "coffee shop interior", "cafe counter indoor", "cozy coffee cup table", "cafe window seat"],
        "camping":       ["campfire night", "tent camping", "forest campfire", "camping nature"],
        # 신규 카테고리
        "airplane":      ["airplane window", "plane cabin", "aircraft interior", "flying clouds"],
        "subway":        ["subway train", "metro train interior", "train window", "train journey"],
        "library":       ["library interior", "quiet study room", "reading room", "books library"],
        "underwater":    ["underwater ocean", "aquarium fish", "deep sea", "underwater coral"],
        "hot_spring":    ["hot spring water", "thermal bath", "onsen steam", "waterfall close"],
        "fireplace_rain":["fireplace cozy", "fireplace rain window", "indoor fire rain", "cozy fireplace"],
        "summer_night":  ["summer night nature", "night insects", "crickets field", "summer dusk"],
        "winter_snow":   ["snowfall nature", "winter forest snow", "snow falling", "blizzard calm"],
        "study_room":    ["study desk lamp", "quiet room night", "desk study", "reading lamp cozy"],
        "stream":        ["forest stream", "mountain creek", "babbling brook", "river stones"],
    }

    def __post_init__(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)