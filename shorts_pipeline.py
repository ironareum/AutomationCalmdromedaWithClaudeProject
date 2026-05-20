"""
2026.05.13 Daily Shorts Pipeline
- 메인 파이프라인과 독립 실행, 카테고리 순환은 used_assets.json 공유
- 음원: main + sub 2레이어만 수집 (point 제외)
- 영상: 2클립
- FFmpeg: 45초 직접 생성 → 9:16 크롭 40초 쇼츠
- YouTube Shorts 매일 18:30 KST 예약 업로드
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from collector.freesound import FreesoundCollector, register_used_session, USED_ASSETS_FILE
from collector.pexels import PexelsCollector
from producer.ffmpeg_producer import VideoProducer
from producer.thumbnail import ThumbnailGenerator
from uploader.youtube import YouTubeUploader
from planner.concept_generator import generate_concept, CATEGORY_TAGS
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


def run_shorts_pipeline():
    cfg        = Config()
    session_id = "shorts_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    work_dir   = cfg.output_dir / session_id
    work_dir.mkdir(parents=True, exist_ok=True)

    log_file     = work_dir / "pipeline.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logging.getLogger().addHandler(file_handler)

    log.info(f"=== Shorts Pipeline Start: {session_id} ===")

    try:
        # Step 1+2: AI 기획 + 음원 수집 (실패 시 최대 3회 다른 카테고리로 재시도)
        failed_categories: list[str] = []
        sound_files: list = []
        concept = None
        sound_collector = FreesoundCollector(
            cfg.freesound_api_key, work_dir, session_id=session_id
        )
        for attempt in range(3):
            log.info(f"Step 1: [AI 기획] 카테고리 선택 및 콘셉트 생성... (시도 {attempt+1}/3)")
            concept = generate_concept(
                api_key=cfg.claude_api_key,
                used_assets_path=USED_ASSETS_FILE,
                duration_hours=1,
                skip_categories=failed_categories,
            )
            log.info(f"생성된 콘셉트: {concept['title']}")

            log.info(f"Step 2: [음원 수집] main + sub 레이어... (시도 {attempt+1}/3)")
            sound_layers = concept.get("sound_layers", {})
            shorts_sound_layers = {
                "main": sound_layers.get("main", []),
                "sub":  sound_layers.get("sub",  []),
            }
            sound_files = sound_collector.collect(
                concept["sounds"],
                count_per_query=2,
                skip_local=True,
                concept=concept,
                sound_layers=shorts_sound_layers,
            )
            if sound_files:
                break
            log.warning(f"음원 수집 실패 ({concept['category']}) — 다음 카테고리 재시도 ({attempt+1}/3)")
            failed_categories.append(concept["category"])

        if not sound_files:
            log.error("3회 재시도 후에도 음원 수집 실패 — 파이프라인 중단")
            return None

        # Step 3: 영상 수집 — 2클립
        log.info("Step 3: [영상 수집] 2클립 수집...")
        video_collector = PexelsCollector(cfg.pexels_api_key, work_dir, session_id=session_id)
        video_files = video_collector.collect(
            concept["category"],
            count=1,
            queries=concept.get("video_queries"),
        )
        if not video_files:
            log.error("영상 수집 실패 — 파이프라인 중단")
            return None

        # Step 4: FFmpeg 45초 영상 생성 → 9:16 크롭 40초 쇼츠
        log.info("Step 4: [영상 제작] 45초 생성 → 40초 9:16 쇼츠...")
        producer = VideoProducer(work_dir)
        produce_result = producer.produce(
            sound_files=sound_files,
            video_files=video_files,
            duration_seconds=45,
            title=concept["title"],
            category=concept.get("category", ""),
        )
        if not produce_result:
            log.error("영상 제작 실패 — 파이프라인 중단")
            return None

        output_video, used_sounds, used_videos, audio_lufs, source_lufs, excluded_sources = produce_result

        shorts_path = producer.extract_shorts_clip(output_video, duration=40)
        if not shorts_path:
            log.error("Shorts 크롭 실패 — 파이프라인 중단")
            return None

        # Step 5: 썸네일
        log.info("Step 5: [썸네일 생성]...")
        thumb_gen = ThumbnailGenerator(work_dir)
        thumbnail = thumb_gen.generate(
            title=concept["title"],
            category=concept["category"],
            video_path=used_videos[0] if used_videos else None,
            title_sub=concept.get("title_sub", "잠잘때 듣기 좋은"),
            subtitle_en=concept.get("subtitle_en", "Healing Music"),
        )

        # Step 6: 메타데이터 저장
        log.info("Step 6: [메타데이터 저장]...")
        shorts_title = concept.get("shorts_title", concept["title"])
        category     = concept.get("category", "")
        cat_tags     = CATEGORY_TAGS.get(category, [])[:2]
        tag_suffix   = " ".join(f"#{t.replace(' ', '')}" for t in cat_tags)
        if tag_suffix:
            full         = f"{shorts_title} {tag_suffix}"
            shorts_title = full[:99] if len(full) >= 100 else full
        shorts_tags = concept["tags"] + ["Shorts", "유튜브쇼츠", "힐링쇼츠", "ASMR쇼츠"]
        shorts_desc = "#Shorts\n\n" + concept.get("description_en", "Relaxing nature sounds for sleep and meditation.")

        metadata = {
            "session_id":   session_id,
            "title":        concept["title"],
            "shorts_title": shorts_title,
            "category":     category,
            "mood":         concept.get("mood", ""),
            "tags":         shorts_tags,
            "created_at":   datetime.now().isoformat(),
            "used_sounds":  [f.name for f in used_sounds],
            "used_videos":  [f.name for f in used_videos],
        }
        meta_path = work_dir / "metadata.json"
        meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

        # Step 7: YouTube Shorts 업로드
        shorts_result = None
        if cfg.upload_enabled:
            log.info("Step 7: [YouTube Shorts 업로드] 예약 공개 업로드...")
            uploader = YouTubeUploader(
                client_secret_path=Path(cfg.youtube_client_secret_path),
                token_path=Path(cfg.youtube_token_path),
            )
            shorts_result = uploader.upload(
                video_path=shorts_path,
                title=shorts_title,
                description=shorts_desc,
                tags=shorts_tags,
                thumbnail_path=thumbnail,
                language=concept.get("language", "ko"),
                hour_kst=cfg.shorts_upload_hour_kst,
                minute_kst=cfg.shorts_upload_minute_kst,
            )
            if shorts_result:
                metadata["youtube_shorts"] = shorts_result
                meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
                log.info(f"Shorts URL: {shorts_result['url']}")
                log.info(f"공개 예약: {shorts_result['publish_at']}")
            else:
                log.warning("Shorts 업로드 실패")
        else:
            log.info("Step 7: UPLOAD_ENABLED=false — 스킵")

        # Step 8: used_assets 등록 (메인 파이프라인과 동일한 파일에 기록)
        register_used_session(
            session_id=session_id,
            title=concept["title"],
            sound_files=used_sounds,
            video_files=used_videos,
            category=category,
            audio_lufs=audio_lufs,
            source_lufs=source_lufs,
            excluded_sources=excluded_sources,
        )

        # Step 9: Google Drive 백업 (메타데이터만)
        log.info("Step 9: [Google Drive 백업]...")
        from pipeline import upload_to_gdrive
        upload_to_gdrive(session_id, work_dir, cfg)

        log.info("=== Shorts Pipeline Complete ===")
        log.info(f"Shorts  : {shorts_path}")
        log.info(f"Thumb   : {thumbnail}")
        log.info(f"Metadata: {meta_path}")
        if shorts_result:
            log.info(f"YouTube : {shorts_result['url']} (공개: {shorts_result['publish_at']})")

        return metadata

    except Exception as e:
        log.exception(f"Shorts Pipeline 예외 발생: {e}")
        return None

    finally:
        logging.getLogger().removeHandler(file_handler)
        file_handler.close()


if __name__ == "__main__":
    result = run_shorts_pipeline()
    if result:
        shorts_info = result.get("youtube_shorts", {})
        print(f"Shorts: {shorts_info.get('url', 'N/A')}")
        print(f"공개 예약: {shorts_info.get('publish_at', 'N/A')}")
    else:
        print("Shorts Pipeline 실패")
        exit(1)
