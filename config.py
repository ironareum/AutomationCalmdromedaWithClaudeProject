"""
Configuration for calmdromeda pipeline
환경변수 or .env 파일로 API 키 관리

2026.03.30 신규 신규 카테고리 추가(12개)
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
        "cafe":          ["cafe window rain", "coffee shop", "cozy interior", "cafe ambience"],
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