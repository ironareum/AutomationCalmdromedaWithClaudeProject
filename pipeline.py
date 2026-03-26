"""
calmdromeda YouTube Automation Pipeline
Phase 1: Asset Collection + FFmpeg Video Production
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path

from collector.freesound import FreesoundCollector
from collector.pexels import PexelsCollector
from producer.ffmpeg_producer import VideoProducer
from producer.thumbnail import ThumbnailGenerator
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


def run_pipeline(concept: dict):
    """
    concept 예시:
    {
        "title": "Heavy Rain on Window with Thunder | 3 Hours Sleep Sounds",
        "category": "rain_thunder",
        "sounds": ["heavy_rain", "thunder_distant", "window_rain"],
        "mood": "stormy cozy",
        "duration_hours": 3,
        "tags": ["rain sounds", "sleep sounds", "thunder", "white noise"]
    }
    """
    cfg = Config()
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    work_dir = cfg.output_dir / session_id
    work_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"=== Pipeline Start: {session_id} ===")
    log.info(f"Concept: {concept['title']}")

    # 1. Collect sound assets
    log.info("Step 1: Collecting sound assets from Freesound...")
    sound_collector = FreesoundCollector(cfg.freesound_api_key, work_dir)
    sound_files = sound_collector.collect(concept["sounds"], count_per_query=3)
    if not sound_files:
        log.error("No sound files collected. Aborting.")
        return None

    # 2. Collect video assets
    log.info("Step 2: Collecting video assets from Pexels...")
    video_collector = PexelsCollector(cfg.pexels_api_key, work_dir)
    video_files = video_collector.collect(concept["category"], count=5)
    if not video_files:
        log.error("No video files collected. Aborting.")
        return None

    # 3. Produce video
    log.info("Step 3: Producing video with FFmpeg...")
    producer = VideoProducer(work_dir)
    output_video = producer.produce(
        sound_files=sound_files,
        video_files=video_files,
        duration_hours=concept["duration_hours"],
        title=concept["title"]
    )
    if not output_video:
        log.error("Video production failed. Aborting.")
        return None

    # 4. Generate thumbnail
    log.info("Step 4: Generating thumbnail...")
    thumb_gen = ThumbnailGenerator(work_dir)
    thumbnail = thumb_gen.generate(
        title=concept["title"],
        category=concept["category"]
    )

    # 5. Save metadata
    metadata = {
        "session_id": session_id,
        "title": concept["title"],
        "tags": concept["tags"],
        "description": generate_description(concept),
        "video_path": str(output_video),
        "thumbnail_path": str(thumbnail),
        "created_at": datetime.now().isoformat()
    }
    meta_path = work_dir / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    log.info(f"=== Pipeline Complete ===")
    log.info(f"Output: {output_video}")
    log.info(f"Thumbnail: {thumbnail}")
    log.info(f"Metadata: {meta_path}")

    return metadata


def generate_description(concept: dict) -> str:
    tags_str = " ".join(f"#{t.replace(' ', '')}" for t in concept["tags"])
    return f"""✨ {concept['title']}

Relax, focus, or drift off to sleep with this {concept['duration_hours']}-hour {concept['mood']} soundscape.
Perfect for studying, working, meditation, or deep sleep.

🎧 Best experienced with headphones or speakers at low volume.

━━━━━━━━━━━━━━━━━━━━━━━━━
🔔 Subscribe for daily calming sounds → @calmdromeda
━━━━━━━━━━━━━━━━━━━━━━━━━

{tags_str}

#calmsounds #sleepsounds #relaxation #naturesounds #whitenoise
"""


if __name__ == "__main__":
    # Test concept
    test_concept = {
        "title": "Heavy Rain & Distant Thunder on Window | 3 Hours Deep Sleep",
        "category": "rain",
        "sounds": ["heavy rain", "thunder storm", "rain on window"],
        "mood": "stormy and cozy",
        "duration_hours": 3,
        "tags": ["rain sounds", "thunder sounds", "sleep sounds", "rain on window", "storm sounds", "white noise", "study music"]
    }
    result = run_pipeline(test_concept)
    if result:
        print(f"\n✅ Success! Video ready: {result['video_path']}")
    else:
        print("\n❌ Pipeline failed. Check logs above.")
