"""
2026.03.26 calmdromeda YouTube Automation Pipeline
2026.03.26 Phase 1: Asset Collection + FFmpeg Video Production
2026.03.28 중복 소스 자동 스킵 (used_assets.json)
2026.03.28 로고 워터마크 자동 삽입
2026.03.28 한글/영어 콘셉트 모두 지원
2026.03.28 로컬 음원 폴백: assets/sounds/{category}/ 폴더 파일 우선 사용

[사운드 수집 우선순위]
1. assets/sounds/{category}/ 폴더에 파일 있으면 → 로컬 파일 우선 사용
2. 로컬 파일 없거나 부족하면 → Freesound API로 자동 수집
3. Freesound도 다운된 경우 → 로컬 파일만으로 진행 (없으면 실패)
"""

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
    concept 예시 (한글):
    {
        "title": "빗소리 ASMR | 3시간 숙면 사운드 | 집중, 공부, 수면",
        "category": "rain",
        "sounds": ["heavy rain", "rain on window", "gentle rain"],
        "mood": "cozy rainy",
        "duration_hours": 3,
        "tags": ["빗소리", "ASMR", "수면음악", "공부음악", "백색소음", "힐링음악"],
        "language": "ko"   # "ko" or "en"
    }
    """
    cfg = Config()
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    work_dir = cfg.output_dir / session_id
    work_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"=== Pipeline Start: {session_id} ===")
    log.info(f"Title: {concept['title']}")

    # 1. 사운드 수집 (로컬 우선 → Freesound API 폴백)
    log.info("Step 1: [사운드 수집] 로컬 폴더 확인 후 필요시 Freesound API 사용...")
    sound_collector = FreesoundCollector(cfg.freesound_api_key, work_dir)
    sound_files = sound_collector.collect(concept["sounds"], count_per_query=3)
    if not sound_files:
        log.error("사운드 파일 없음. assets/sounds/{category}/ 폴더에 음원을 넣거나 Freesound API를 확인하세요.")
        return None

    # 2. 영상 수집
    log.info("Step 2: [영상 수집] Collecting video assets from Pexels...")
    video_collector = PexelsCollector(cfg.pexels_api_key, work_dir)
    video_files = video_collector.collect(concept["category"], count=5)
    if not video_files:
        log.error("No video files collected. Aborting.")
        return None

    # 3. 영상 제작 (로고 오버레이 포함)
    log.info("Step 3: [영상 제작] Producing video with FFmpeg...")
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

    # 4. 썸네일 생성 — 수집된 영상 중 첫 번째 파일의 첫 프레임을 배경으로 사용
    log.info("Step 4: [썸네일 생성] Generating thumbnail...")
    thumb_gen = ThumbnailGenerator(work_dir)
    thumbnail = thumb_gen.generate(
        title=concept["title"],
        category=concept["category"],
        video_path=video_files[0] if video_files else None,
        title_sub=concept.get("title_sub", "잠잘때 듣기 좋은"),
        subtitle_en=concept.get("subtitle_en", "Healing Music"),
    )

    # 5. 메타데이터 저장
    log.info("Step 5: [메타데이터 저장] Saving metadata...")
    language = concept.get("language", "ko")
    metadata = {
        "session_id": session_id,
        "title": concept["title"],
        "tags": concept["tags"],
        "description": generate_description(concept),
        "language": language,
        "video_path": str(output_video),
        "thumbnail_path": str(thumbnail),
        "created_at": datetime.now().isoformat()
    }
    meta_path = work_dir / "metadata.json"
    # encoding="utf-8" 명시 → Windows cp949 에러 방지
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    log.info("=== Pipeline Complete ===")
    log.info(f"Video   : {output_video}")
    log.info(f"Thumb   : {thumbnail}")
    log.info(f"Metadata: {meta_path}")

    return metadata


def generate_description(concept: dict) -> str:
    language = concept.get("language", "ko")
    hours = concept["duration_hours"]
    mood = concept.get("mood", "calming")

    if language == "ko":
        tags_str = " ".join(f"#{t.replace(' ', '')}" for t in concept["tags"])
        return f"""{concept['title']}

편안하게 쉬거나, 집중하거나, 깊은 잠에 빠져들어 보세요.
{hours}시간의 {mood} 사운드스케이프입니다.
공부, 업무, 명상, 숙면에 최적화되어 있습니다.

🎧 이어폰이나 스피커로 들으시면 더욱 좋습니다.

━━━━━━━━━━━━━━━━━━━━━━━━━
🔔 매일 새로운 힐링 사운드 → @Calmdromeda 구독
━━━━━━━━━━━━━━━━━━━━━━━━━

{tags_str}

#힐링음악 #ASMR #수면음악 #백색소음 #자연소리 #집중음악
"""
    else:
        tags_str = " ".join(f"#{t.replace(' ', '')}" for t in concept["tags"])
        return f"""{concept['title']}

Relax, focus, or drift off to sleep with this {hours}-hour {mood} soundscape.
Perfect for studying, working, meditation, or deep sleep.

🎧 Best experienced with headphones or speakers at low volume.

━━━━━━━━━━━━━━━━━━━━━━━━━
🔔 Subscribe for daily calming sounds → @Calmdromeda
━━━━━━━━━━━━━━━━━━━━━━━━━

{tags_str}

#calmsounds #sleepsounds #relaxation #naturesounds #whitenoise
"""


if __name__ == "__main__":
    # ===== 한글 콘셉트 테스트 =====
    test_concept = {
        "title": "빗소리 ASMR | 1시간 숙면 & 집중 사운드 | 공부할 때 듣기 좋은 음악",
        "category": "rain",
        "sounds": ["heavy rain", "rain on window", "gentle rain"],
        "mood": "cozy rainy",
        "duration_hours": 0.02,              # 1
        "title_sub": "공부할 때 듣기 좋은",     # 썸네일 상단 부제목
        "subtitle_en": "Rain Sounds",        # 썸네일 하단 영문
        "tags": ["빗소리", "ASMR", "수면음악", "공부음악", "백색소음", "힐링음악", "빗소리ASMR"],
        "language": "ko"
    }

    # ===== 영어 콘셉트로 바꾸려면 아래 주석 해제 =====
    # test_concept = {
    #     "title": "Heavy Rain & Distant Thunder | 3 Hours Deep Sleep Sounds",
    #     "category": "rain_thunder",
    #     "sounds": ["heavy rain", "thunder storm", "rain on window"],
    #     "mood": "stormy and cozy",
    #     "duration_hours": 3,
    #     "tags": ["rain sounds", "thunder", "sleep sounds", "white noise", "study music"],
    #     "language": "en"
    # }

    result = run_pipeline(test_concept)
    if result:
        print(f"\nSuccess! Video: {result['video_path']}")
    else:
        print("\nPipeline failed. Check logs.")