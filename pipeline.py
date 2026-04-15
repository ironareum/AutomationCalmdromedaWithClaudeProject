"""
2026.03.26 calmdromeda YouTube Automation Pipeline
2026.03.26 Phase 1: Asset Collection + FFmpeg Video Production
2026.03.28 중복 소스 자동 스킵 (used_assets.json)
2026.03.28 로고 워터마크 자동 삽입
2026.03.28 한글/영어 콘셉트 모두 지원
2026.03.28 로컬 음원 폴백: assets/sounds/{category}/ 폴더 파일 우선 사용
2026.03.29 오디오 -14 LUFS 정규화 (YouTube 권장)
2026.03.29 디스크 사용량 최소화 - 임시 파일 단계별 즉시 삭제, 실 사용 파일만 output 적재
2026.03.29 output/{session_id}/pipeline.log 로그 파일 자동 생성
2026.03.29 used_assetss.json 포맷형식 변경
2026.03.29 YouTube 업로드

2026.03.29 [Phase2] AI 기획 자동화 (Claude API) + sound,video 쿼리에도 적용
2026.04.01 fix: 사운드 타겟팅 강화, 영상 재사용 모드 추가, 그룹 기반 카테고리 로테이션
2026.04.01 재사용 모드에서는 로컬 파일 무시하고 API에서만 수집
2026.04.02 feat: AI 사운드 검증 추가 (컨셉 일치율 향상), 계절 키워드 제거
2026.04.04 feat: 3레이어 사운드 구조 (main/sub/point) + 볼륨 랜덤화 + calm 쿼리 강화
2026.04.07 feat: 제목/설명 영문 추가 (글로벌 타겟팅)
2026.04.07 feat: 썸네일 단독 생성 스크립트 추가
2026.04.07 feat: --category 옵션 추가(로컬수행용)
"""

import argparse
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from collector.freesound import FreesoundCollector, register_used_session
from collector.pexels import PexelsCollector
from producer.ffmpeg_producer import VideoProducer
from producer.thumbnail import ThumbnailGenerator
from uploader.youtube import YouTubeUploader
from uploader.instagram import InstagramUploader, build_caption
from planner.concept_generator import generate_concept, CATEGORY_SOUNDS as CATEGORY_SOUNDS_FOR_REUSE, CATEGORY_TAGS
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

    # 파일 로그 핸들러 등록 — output/{session_id}/pipeline.log
    log_file = work_dir / "pipeline.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)  # 파일엔 DEBUG까지 전부 기록
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s"
    ))
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)

    log.info(f"=== Pipeline Start: {session_id} ===")
    log.info(f"Title: {concept['title']}")
    log.info(f"Log file: {log_file}")

    try:
        # 1. 사운드 수집 (로컬 우선 → Freesound API 폴백)
        log.info("Step 1: [사운드 수집] 로컬 폴더 확인 후 필요시 Freesound API 사용...")
        sound_collector = FreesoundCollector(cfg.freesound_api_key, work_dir, session_id=session_id)
        # 재사용 모드에서는 로컬 음원 무시 (카테고리 불일치 방지)
        skip_local = bool(concept.get("_reuse_video_session"))
        # 메인/서브/포인트 레이어 구조로 수집
        sound_layers = concept.get("sound_layers")
        sound_files = sound_collector.collect(
            concept["sounds"],
            count_per_query=3,
            skip_local=skip_local,
            concept=concept,
            sound_layers=sound_layers,
        )
        if not sound_files:
            log.error("사운드 파일 없음. assets/sounds/{category}/ 폴더에 음원을 넣거나 Freesound API를 확인하세요.")
            return None

        # 2. 영상 수집
        log.info("Step 2: [영상 수집] Collecting video assets from Pexels...")
        reuse_session = concept.get("_reuse_video_session")
        if reuse_session:
            # 영상 재사용: 기존 세션 영상 복사
            reuse_dir = cfg.output_dir / reuse_session
            old_videos_dir = reuse_dir / "videos"
            new_videos_dir = work_dir / "videos"
            new_videos_dir.mkdir(parents=True, exist_ok=True)
            video_files = []
            if old_videos_dir.exists():
                for vf in sorted(old_videos_dir.glob("*.mp4")):
                    dest = new_videos_dir / vf.name
                    shutil.copy2(str(vf), str(dest))
                    video_files.append(dest)
                log.info(f"영상 재사용: {len(video_files)}개 복사 ({reuse_session})")
            else:
                log.warning(f"기존 영상 폴더 없음: {old_videos_dir} — 새로 수집")
                video_files = []
            if not video_files:
                video_collector = PexelsCollector(cfg.pexels_api_key, work_dir, session_id=session_id)
                video_files = video_collector.collect(concept["category"], count=5)
        else:
            video_collector = PexelsCollector(cfg.pexels_api_key, work_dir, session_id=session_id)
            video_files = video_collector.collect(
                concept["category"],
                count=5,
                queries=concept.get("video_queries"),  # AI 생성 쿼리, 없으면 config 기본값
            )
        if not video_files:
            log.error("No video files collected. Aborting.")
            return None

        # 3. 영상 제작 (로고 오버레이 포함)
        log.info("Step 3: [영상 제작] Producing video with FFmpeg...")
        producer = VideoProducer(work_dir)
        produce_result = producer.produce(
            sound_files=sound_files,
            video_files=video_files,
            duration_hours=concept["duration_hours"],
            title=concept["title"],
            category=concept.get("category", ""),
        )
        if not produce_result:
            log.error("Video production failed. Aborting.")
            return None

        # produce()가 반환한 실제 사용 파일 목록으로 정리
        output_video, used_sounds, used_videos = produce_result
        log.info(f"실제 사용: sounds={[f.name for f in used_sounds]}, "
                 f"videos={[f.name for f in used_videos]}")

        _cleanup_assets(
            used_sounds=used_sounds,
            used_videos=used_videos,
            work_dir=work_dir,
            sound_collector=sound_collector,
        )

        # 실제 사용한 소스를 used_assets.json에 등록 (session_id 키)
        register_used_session(
            session_id=session_id,
            title=concept["title"],
            sound_files=used_sounds,
            video_files=used_videos,
            category=concept.get("category", ""),
        )

        # 4. 썸네일 생성 — 수집된 영상 중 첫 번째 파일의 첫 프레임을 배경으로 사용
        log.info("Step 4: [썸네일 생성] Generating thumbnail...")
        thumb_gen = ThumbnailGenerator(work_dir)
        thumbnail = thumb_gen.generate(
            title=concept["title"],
            category=concept["category"],
            video_path=used_videos[0] if used_videos else None,
            title_sub=concept.get("title_sub", "잠잘때 듣기 좋은"),
            subtitle_en=concept.get("subtitle_en", "Healing Music"),
        )

        # 5. 메타데이터 저장
        log.info("Step 5: [메타데이터 저장] Saving metadata...")
        language = concept.get("language", "ko")
        metadata = {
            "session_id": session_id,
            "title": concept["title"],
            "category": concept.get("category", ""),
            "mood": concept.get("mood", ""),
            "duration_hours": concept.get("duration_hours", 1),
            "title_sub": concept.get("title_sub", ""),
            "subtitle_en": concept.get("subtitle_en", ""),
            "tags": concept["tags"],
            "description": generate_description(concept),
            "language": language,
            "video_path": str(output_video),
            "thumbnail_path": str(thumbnail),
            "created_at": datetime.now().isoformat(),
            "used_sounds": [f.name for f in used_sounds],
            "used_videos": [f.name for f in used_videos],
        }
        meta_path = work_dir / "metadata.json"
        meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

        # 6. YouTube 업로드 (UPLOAD_ENABLED=true 일 때만)
        upload_result = None
        if cfg.upload_enabled:
            log.info("Step 6: [YouTube 업로드] 예약 공개 업로드 시작...")
            uploader = YouTubeUploader(
                client_secret_path=Path(cfg.youtube_client_secret_path),
                token_path=Path(cfg.youtube_token_path),
            )
            upload_result = uploader.upload(
                video_path=output_video,
                title=concept["title"],
                description=metadata["description"],
                tags=concept["tags"],
                thumbnail_path=thumbnail,
                language=concept.get("language", "ko"),
                hour_kst=cfg.upload_hour_kst,
                minute_kst=cfg.upload_minute_kst,
            )
            if upload_result:
                metadata["youtube"] = upload_result
                # metadata.json 업데이트 (youtube 정보 추가)
                meta_path.write_text(
                    json.dumps(metadata, indent=2, ensure_ascii=False),
                    encoding="utf-8"
                )
                log.info(f"YouTube URL: {upload_result['url']}")
                log.info(f"공개 예약: {upload_result['publish_at']}")
            else:
                log.warning("YouTube 업로드 실패 — 영상은 로컬에 저장됨")
        else:
            log.info("Step 6: [YouTube 업로드] UPLOAD_ENABLED=false — 스킵")

        # 7. Google Drive 백업
        log.info("Step 7: [Google Drive 백업] rclone 업로드...")
        upload_to_gdrive(session_id, work_dir, cfg)

        # 8. 쇼츠 클립 추출 + YouTube Shorts 업로드
        shorts_result = None
        shorts_path   = None  # Step 9 Instagram에서도 접근 가능하도록 블록 밖에서 초기화
        if cfg.upload_enabled:
            log.info("Step 8: [쇼츠 제작] Extracting Shorts clip...")
            shorts_path = producer.extract_shorts_clip(output_video, duration=40)

            if shorts_path:
                log.info("Step 8: [쇼츠 업로드] YouTube Shorts 업로드 시작...")
                # 쇼츠용 제목: 감성적 shorts_title + 카테고리 태그 (100자 미만)
                shorts_title = concept.get("shorts_title", concept["title"])
                category = concept.get("category", "")
                cat_tags = CATEGORY_TAGS.get(category, [])[:2]  # 한국어 태그 최대 2개
                tag_suffix = " ".join(f"#{t.replace(' ', '')}" for t in cat_tags)
                if tag_suffix:
                    full = f"{shorts_title} {tag_suffix}"
                    shorts_title = full[:99] if len(full) >= 100 else full

                # 쇼츠 태그 (원본 태그 + Shorts 태그)
                shorts_tags = concept["tags"] + ["Shorts", "유튜브쇼츠", "힐링쇼츠", "ASMR쇼츠"]

                # 쇼츠 설명 (title 중복 제거 — description 첫 줄이 이미 title)
                shorts_desc = "#Shorts\n\n" + metadata["description"]

                shorts_uploader = YouTubeUploader(
                    client_secret_path=Path(cfg.youtube_client_secret_path),
                    token_path=Path(cfg.youtube_token_path),
                )
                shorts_result = shorts_uploader.upload(
                    video_path=shorts_path,
                    title=shorts_title,
                    description=shorts_desc,
                    tags=shorts_tags,
                    thumbnail_path=thumbnail,
                    language=concept.get("language", "ko"),
                    hour_kst=cfg.upload_hour_kst,
                    minute_kst=cfg.upload_minute_kst,
                )
                if shorts_result:
                    metadata["youtube_shorts"] = shorts_result
                    meta_path.write_text(
                        json.dumps(metadata, indent=2, ensure_ascii=False),
                        encoding="utf-8"
                    )
                    log.info(f"Shorts URL: {shorts_result['url']}")
                else:
                    log.warning("Shorts 업로드 실패 — 풀영상 업로드는 유지됨")
            else:
                log.warning("Shorts 클립 추출 실패 — 스킵")
        else:
            log.info("Step 7: [쇼츠] UPLOAD_ENABLED=false — 스킵")

        # 9. Instagram Reels 업로드
        instagram_result = None
        if cfg.instagram_enabled and cfg.instagram_access_token and cfg.instagram_user_id:
            if shorts_path and shorts_path.exists():
                log.info("Step 9: [Instagram Reels] 쇼츠 영상 업로드 시작...")
                ig_uploader = InstagramUploader(
                    access_token=cfg.instagram_access_token,
                    user_id=cfg.instagram_user_id,
                )
                # 토큰 갱신 시도 (60일 연장)
                ig_uploader.refresh_token()

                youtube_url = upload_result.get("url") if upload_result else None
                caption = build_caption(concept, youtube_url=youtube_url)
                instagram_result = ig_uploader.post_reel(shorts_path, caption)

                if instagram_result:
                    metadata["instagram"] = instagram_result
                    meta_path.write_text(
                        json.dumps(metadata, indent=2, ensure_ascii=False),
                        encoding="utf-8"
                    )
                    log.info(f"Instagram Reel post_id: {instagram_result['post_id']}")
                else:
                    log.warning("Instagram Reels 업로드 실패 — YouTube 업로드는 유지됨")
            else:
                log.warning("Step 9: [Instagram Reels] Shorts 파일 없음 — 스킵")
        else:
            log.info("Step 9: [Instagram Reels] INSTAGRAM_ENABLED=false 또는 토큰 미설정 — 스킵")

        log.info("=== Pipeline Complete ===")
        log.info(f"Video   : {output_video}")
        log.info(f"Thumb   : {thumbnail}")
        log.info(f"Metadata: {meta_path}")
        log.info(f"Log     : {log_file}")
        if upload_result:
            log.info(f"YouTube : {upload_result['url']} (공개: {upload_result['publish_at']})")
        if shorts_result:
            log.info(f"Shorts  : {shorts_result['url']} (공개: {shorts_result['publish_at']})")
        if instagram_result:
            log.info(f"Instagram: post_id={instagram_result['post_id']}")

        return metadata

    except Exception as e:
        log.exception(f"Pipeline 예외 발생: {e}")
        return None

    finally:
        # 성공/실패/예외 모두 핸들러 해제 (다음 실행 시 중복 방지)
        root_logger.removeHandler(file_handler)
        file_handler.close()


def _cleanup_assets(
    used_sounds: list,
    used_videos: list,
    work_dir: Path,
    sound_collector,
):
    """
    produce() 완료 후 실제 사용한 파일만 남기고 정리

    [로컬 음원] assets/sounds/{category}/ 에서 가져온 파일
      → assets/sounds/_used/{session_id}/ 로 이동 (재사용 방지)

    [output/sounds] 다운받았지만 실제로 안 쓴 API 음원
      → 삭제 (used_sounds에 없는 파일)

    [output/videos] 다운받았지만 실제로 안 쓴 영상
      → 삭제 (used_videos에 없는 파일)
    """
    from collector.freesound import LOCAL_SOUNDS_DIR, SOUND_EXTENSIONS

    used_sound_names = {f.name for f in used_sounds}
    used_video_names = {f.name for f in used_videos}

    # 1. 로컬 음원 → _used/ 이동 (assets/sounds/ 하위에서 온 파일만)
    for sound_path in used_sounds:
        if LOCAL_SOUNDS_DIR in sound_path.parents:
            sound_collector.local.move_to_used(sound_path)

    # 2. output/sounds/ — 실제 사용 안 한 API 다운로드 파일 삭제
    sounds_dir = work_dir / "sounds"
    if sounds_dir.exists():
        for f in sounds_dir.iterdir():
            if f.suffix.lower() in SOUND_EXTENSIONS and f.name not in used_sound_names:
                try:
                    f.unlink()
                    log.info(f"Unused sound deleted: {f.name}")
                except Exception as e:
                    log.warning(f"삭제 실패 {f.name}: {e}")

    # 3. output/videos/ — 실제 사용 안 한 영상 파일 삭제
    videos_dir = work_dir / "videos"
    if videos_dir.exists():
        for f in videos_dir.iterdir():
            if f.suffix.lower() == ".mp4" and f.name not in used_video_names:
                try:
                    f.unlink()
                    log.info(f"Unused video deleted: {f.name}")
                except Exception as e:
                    log.warning(f"삭제 실패 {f.name}: {e}")



def upload_to_gdrive(session_id: str, work_dir: Path, cfg) -> bool:
    """rclone으로 Google Drive에 업로드 (음원·영상 파일 제외)"""
    import shutil, subprocess

    # rclone 실행 파일 찾기 (로컬: 루트의 rclone.exe, Actions: PATH의 rclone)
    rclone_bin = "rclone"
    local_rclone = Path(__file__).parent / "rclone.exe"
    if local_rclone.exists():
        rclone_bin = str(local_rclone)

    # rclone 설치 여부 확인
    if not shutil.which(rclone_bin) and rclone_bin == "rclone":
        log.warning("rclone 없음 — Google Drive 업로드 스킵")
        return False

    # gdrive 리모트 설정 확인
    try:
        check = subprocess.run(
            [rclone_bin, "listremotes"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=30
        )
        remotes = check.stdout.strip().splitlines()
        if "gdrive:" not in remotes:
            log.error(
                f"rclone 설정에 'gdrive' 리모트가 없습니다. "
                f"현재 리모트: {remotes or '없음'} — "
                f"RCLONE_CONF 시크릿에 [gdrive] 섹션이 포함되어 있는지 확인하세요."
            )
            return False
    except Exception as e:
        log.error(f"rclone listremotes 실패: {e}")
        return False

    remote_path = f"gdrive:Calmdromeda/{session_id}"

    # 음원·영상 파일은 제외 (log 파일에 소스 출처 기록됨)
    # *.ext: 루트 포함 모든 depth 제외 (**/*.ext는 루트 파일 미매칭)
    exclude_media = [
        "--exclude=*.mp3",
        "--exclude=*.wav",
        "--exclude=*.flac",
        "--exclude=*.aac",
        "--exclude=*.ogg",
        "--exclude=*.m4a",
        "--exclude=*.mp4",
        "--exclude=*.mkv",
        "--exclude=*.avi",
        "--exclude=*.mov",
        "--exclude=*.webm",
        "--exclude=temp/**",
    ]

    try:
        result = subprocess.run(
            [rclone_bin, "copy", str(work_dir), remote_path,
             "--progress", "--transfers=4"] + exclude_media,
            capture_output=True, encoding="utf-8", errors="replace", timeout=600
        )
        if result.returncode == 0:
            log.info(f"Google Drive 업로드 완료: {remote_path} (음원·영상 제외)")
            return True
        else:
            log.error(f"rclone 업로드 실패: {result.stderr[:500]}")
            return False
    except FileNotFoundError:
        log.warning("rclone 없음 — Google Drive 업로드 스킵")
        return False
    except Exception as e:
        log.error(f"rclone 업로드 오류: {e}")
        return False


def generate_description(concept: dict) -> str:
    language = concept.get("language", "ko")
    hours = concept["duration_hours"]
    mood = concept.get("mood", "calming")
    desc_en = concept.get("description_en", "")

    tags_str = " ".join(f"#{t.replace(' ', '')}" for t in concept["tags"])

    ko_body = f"""편안하게 쉬거나, 집중하거나, 깊은 잠에 빠져들어 보세요.
{hours}시간의 {mood} 사운드스케이프입니다.
공부, 업무, 명상, 숙면에 최적화되어 있습니다."""

    en_section = desc_en if desc_en else f"""Relax, focus, or drift off to sleep with this {hours}-hour soundscape.
Perfect for studying, working, meditation, or deep sleep.
Best experienced with headphones. 🎧

━━━━━━━━━━━━━━━━━━━━━━━━━
🔔 Subscribe for daily calming sounds → @Calmdromeda
━━━━━━━━━━━━━━━━━━━━━━━━━"""

    return f"""{concept['title']}

{ko_body}

{en_section}

🎧 이어폰이나 스피커로 들으시면 더욱 좋습니다.

━━━━━━━━━━━━━━━━━━━━━━━━━
🔔 매일 새로운 힐링 사운드 → @Calmdromeda 구독
━━━━━━━━━━━━━━━━━━━━━━━━━

{tags_str}

#힐링음악 #ASMR #수면음악 #백색소음 #자연소리 #집중음악 #calmsounds #sleepsounds #relaxation #naturesounds
"""


if __name__ == "__main__":
    cfg = Config()

    # ════════════════════════════════════════════════════════════════
    # ▼▼▼ 모드 선택 플래그 ▼▼▼
    USE_AI_PLANNER = True   # True: Claude AI 자동 기획 / False: 수동 콘셉트
    # ════════════════════════════════════════════════════════════════

    # ── CLI 인자 파싱 ─────────────────────────────────────────────────
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", type=str, default=None,
                        help="카테고리 직접 지정 (e.g. bath_house, cave_water). 지정 시 로컬 소스 우선 사용")
    parser.add_argument("--reuse-session", type=str, default=None,
                        help="기존 세션 영상 재사용 (사운드만 새로 제작). 예: 20260331_000300")
    args, _ = parser.parse_known_args()

    if args.reuse_session:
        # ── 영상 재사용 모드 ──────────────────────────────────────────
        reuse_session_id = args.reuse_session
        reuse_dir = cfg.output_dir / reuse_session_id
        metadata_path = reuse_dir / "metadata.json"

        if not reuse_dir.exists():
            log.error("=" * 60)
            log.error("영상 재사용은 로컬 실행에서만 가능합니다.")
            log.error(f"output/{reuse_session_id}/ 폴더가 없습니다.")
            log.error("GitHub Actions에서는 실행 후 output/ 폴더가 삭제됩니다.")
            log.error("로컬에서 실행하거나 run_local.bat 을 사용하세요.")
            log.error("=" * 60)
            raise SystemExit(1)

        if not metadata_path.exists():
            log.error(f"metadata.json 없음: {metadata_path}")
            raise SystemExit(1)

        with open(metadata_path, encoding="utf-8") as f:
            meta = json.load(f)

        log.info(f"영상 재사용 모드: {reuse_session_id}")
        log.info(f"기존 제목: {meta.get('title', '?')}")
        log.info(f"기존 영상: {meta.get('used_videos', [])}")

        # 기존 concept 로드 (카테고리/제목 유지)
        concept = {
            "title":         meta.get("title", ""),
            "category":      meta.get("category", "rain"),
            "sounds":        meta.get("used_sounds", []),
            "video_queries": meta.get("video_queries"),
            "mood":          meta.get("mood", "calm"),
            "duration_hours": meta.get("duration_hours", 1),
            "title_sub":     meta.get("title_sub", "힐링 사운드"),
            "subtitle_en":   meta.get("subtitle_en", "Healing Music"),
            "tags":          meta.get("tags", []),
            "language":      meta.get("language", "ko"),
            "_reuse_video_session": reuse_session_id,  # 재사용 플래그
        }

        # 새 사운드로 교체할지 여부 확인
        log.info("사운드를 새로 수집해서 교체합니다.")
        category = concept.get("category", "")
        if not category:
            # metadata에 category 없으면 thumbnail 파일명에서 추론
            thumb = meta.get("thumbnail_path", "")
            for cat in CATEGORY_SOUNDS_FOR_REUSE.keys():
                if cat in thumb:
                    category = cat
                    break
            if category:
                log.info(f"thumbnail에서 카테고리 추론: {category}")
                concept["category"] = category
            else:
                log.warning("카테고리 추론 실패 — used_sounds 쿼리 그대로 사용")
        sound_queries = CATEGORY_SOUNDS_FOR_REUSE.get(category, [])
        if sound_queries:
            concept["sounds"] = sound_queries
            log.info(f"카테고리 '{category}' 사운드 쿼리 적용: {sound_queries[:3]}")
        else:
            log.warning(f"카테고리 '{category}' 쿼리 없음 — used_sounds 그대로 사용")

    elif USE_AI_PLANNER:
        # ── AI 자동 기획 모드 ─────────────────────────────────────────
        # Claude Haiku가 계절/카테고리 로테이션/기존 업로드 기반으로 자동 생성
        # .env에 ANTHROPIC_API_KEY 필요
        from collector.freesound import USED_ASSETS_FILE
        concept = generate_concept(
            api_key=cfg.claude_api_key,
            used_assets_path=USED_ASSETS_FILE,
            duration_hours=1,
            language="ko",
            force_category=args.category,  # --category 지정 시 해당 카테고리로 강제 기획
        )
    else:
        # ── 수동 콘셉트 모드 (기존 방식) ─────────────────────────────
        # USE_AI_PLANNER = False 일 때 아래 콘셉트 그대로 사용
        concept = {
            "title": "빗소리 ASMR | 1시간 숙면 & 집중 사운드 | 공부할 때 듣기 좋은 음악",
            "category": "rain",
            "sounds": ["heavy rain", "rain on window", "gentle rain"],
            "mood": "cozy rainy",
            "duration_hours": 1,
            "title_sub": "공부할 때 듣기 좋은",
            "subtitle_en": "Rain Sounds",
            "tags": ["빗소리", "ASMR", "수면음악", "공부음악", "백색소음", "힐링음악"],
            "language": "ko"
        }
        # ── 영어 콘셉트로 바꾸려면 아래 주석 해제 ─────────────────────
        # concept = {
        #     "title": "Heavy Rain & Distant Thunder | 3 Hours Deep Sleep Sounds",
        #     "category": "rain_thunder",
        #     "sounds": ["heavy rain", "thunder storm", "rain on window"],
        #     "mood": "stormy and cozy",
        #     "duration_hours": 3,
        #     "tags": ["rain sounds", "thunder", "sleep sounds", "white noise"],
        #     "language": "en"
        # }

    result = run_pipeline(concept)
    if result:
        print(f"\nSuccess! Video: {result['video_path']}")
        if result.get("youtube"):
            print(f"YouTube: {result['youtube']['url']}")
            print(f"공개 예약: {result['youtube']['publish_at']}")
    else:
        print("\nPipeline failed. Check logs.")