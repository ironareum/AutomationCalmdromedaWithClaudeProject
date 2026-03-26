"""
Configuration for calmdromeda pipeline
환경변수 or .env 파일로 API 키 관리
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

    # Upload schedule (Phase 2)
    upload_days: list = ["monday", "wednesday", "friday"]  # 주 3회
    upload_hour: int = 14  # UTC 14:00 (한국 23:00, 미국 동부 10:00)

    # Category → Pexels search query mapping
    category_queries = {
        "rain": ["rain window", "rainy day", "rain drops glass", "storm rain"],
        "rain_thunder": ["thunderstorm", "dark storm", "lightning rain", "rainy night"],
        "ocean": ["ocean waves", "beach waves", "sea waves night", "calm ocean"],
        "forest": ["forest nature", "misty forest", "green forest", "forest morning"],
        "birds": ["birds nature", "morning forest", "peaceful garden", "bird wildlife"],
        "white_noise": ["abstract calm", "minimalist nature", "soft light nature", "peaceful landscape"],
        "cafe": ["cafe window rain", "coffee shop", "cozy interior", "cafe ambience"],
        "camping": ["campfire night", "tent camping", "forest campfire", "camping nature"],
    }

    def __post_init__(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
