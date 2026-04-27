"""
Zen/Oriental 8h 롱폼 + 60s 숏폼 파이프라인
2026.04.27 신규 — pipeline.py와 완전 분리

실행:
  python pipeline_zen.py --mode longform   # 8h 롱폼 (로컬 권장)
  python pipeline_zen.py --mode shorts     # 60s 숏폼 (Actions 가능)
  python pipeline_zen.py --mode both       # 롱폼 제작 후 숏폼 추출 (로컬)
  python pipeline_zen.py --category moktak_melodic

[FFmpeg 최적화 — pipeline.py 대비]
  기존: normalize → loop → merge → logo = 인코딩 3회
  변경: normalize → (loop + logo 동시) → merge(copy) = 인코딩 2회
  preset medium → fast: 약 35% 단축
  예상 8h 로컬 처리시간: 3~5시간 (PC 사양 의존)
"""

import argparse
import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from collector.freesound import (
    FreesoundCollector, register_used_session, USED_ASSETS_FILE,
)
from collector.pexels import PexelsCollector
from collector.pixabay import PixabayMusicCollector
from config import Config
from planner.zen_concept import generate_zen_concept
from producer.ffmpeg_producer import VideoProducer, LOGO_PATH, LOGO_HEADING_PATH
from producer.thumbnail import ThumbnailGenerator
from uploader.youtube import YouTubeUploader

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

DURATION_LONGFORM = 8 * 3600   # 28800초
DURATION_SHORTS   = 60          # 60초


# ── FFmpeg 유틸 ────────────────────────────────────────────────────────────

def _run(cmd: list, desc: str = "") -> bool:
    log.info(f"FFmpeg: {desc}")
    r = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        log.error(f"FFmpeg 실패:\n{r.stderr[-800:]}")
        return False
    return True


def _logo_inputs_and_filter(producer: VideoProducer) -> tuple[list, str, str]:
    """
    로고 입력 옵션 + filter_complex + 최종 맵 레이블 반환.
    비디오 입력은 항상 input[0]으로 가정.
    """
    has_h = LOGO_HEADING_PATH.exists()
    has_c = LOGO_PATH.exists()

    if not has_h and not has_c:
        return [], "", "0:v"

    extra_inputs: list[str] = []
    parts: list[str] = []
    idx = 1
    prev = "0:v"

    if has_h:
        logo_png = producer._prepare_logo_png(LOGO_HEADING_PATH)
        extra_inputs += ["-i", str(logo_png)]
        parts.append(f"[{idx}:v]scale=iw*0.17:-2[lh]")
        parts.append(f"[{prev}][lh]overlay=12:12[vh]")
        prev = "vh"
        idx += 1

    if has_c:
        extra_inputs += ["-i", str(LOGO_PATH)]
        parts.append(f"[{idx}:v]scale=180:-2,format=rgba,colorchannelmixer=aa=0.6[lc]")
        parts.append(f"[{prev}][lc]overlay=W-w-20:H-h-20[vout]")
        final = "vout"
    else:
        # heading만 있는 경우 출력 레이블 통일
        parts[-1] = parts[-1].replace(f"[{prev}]", f"[{prev}]").rsplit("[", 1)[0] + "[vout]"
        final = "vout"

    return extra_inputs, ";".join(parts), final


# ── Step 1: 음원 수집 ─────────────────────────────────────────────────────

def collect_audio(concept: dict, work_dir: Path, cfg: Config) -> list[Path]:
    """Pixabay Music 우선 → 실패 시 Freesound 폴백"""
    pixabay_key = os.environ.get("PIXABAY_API_KEY", "")

    if pixabay_key:
        log.info("Step 1a: [음원] Pixabay Music API...")
        pb = PixabayMusicCollector(api_key=pixabay_key, work_dir=work_dir)
        sounds = pb.collect(concept["pixabay_queries"], count=1)
        if sounds:
            return sounds
        log.warning("Pixabay 수집 실패 → Freesound 폴백")
    else:
        log.info("PIXABAY_API_KEY 없음 → Freesound 폴백")

    log.info("Step 1b: [음원] Freesound...")
    fc = FreesoundCollector(
        api_key=cfg.freesound_api_key,
        work_dir=work_dir,
        session_id=work_dir.name,
    )
    return fc.collect(
        queries=concept["freesound_fallback"],
        count_per_query=2,
        skip_local=True,
        concept=concept,
    )


# ── Step 2: 영상 수집 (단일 최적 클립) ────────────────────────────────────

def collect_best_video(concept: dict, work_dir: Path, cfg: Config) -> Path | None:
    """Pexels 쿼리에서 가장 긴 단일 클립 선택"""
    pc = PexelsCollector(
        api_key=cfg.pexels_api_key,
        work_dir=work_dir,
        session_id=work_dir.name,
    )
    candidates: list[tuple[int, Path]] = []

    for query in concept.get("pexels_queries", []):
        for video in pc.search(query, count=4)[:2]:
            path = pc.download(video)
            if path:
                candidates.append((int(video.get("duration", 0)), path))

    if not candidates:
        log.error("영상 후보 없음")
        return None

    candidates.sort(reverse=True)
    best_dur, best = candidates[0]
    log.info(f"최적 클립 선택: {best.name} ({best_dur}s)")

    for _, p in candidates[1:]:
        try:
            p.unlink()
        except Exception:
            pass

    return best


# ── Step 3-A: 8h 롱폼 제작 ────────────────────────────────────────────────

def produce_longform(
    sound_files: list[Path],
    video_file: Path,
    concept: dict,
    work_dir: Path,
) -> tuple | None:
    """
    2-pass 최적화:
      Pass 1: 단일 클립 normalize → stream_loop + logo overlay (8h 인코딩, preset fast)
      Pass 2: video + audio merge (stream copy, 빠름)
    반환: (output_path, actual_sounds, audio_lufs, source_lufs, excluded)
    """
    producer = VideoProducer(work_dir)
    temp_dir = work_dir / "temp"
    temp_dir.mkdir(exist_ok=True)

    # 오디오 믹싱 (기존 VideoProducer 재사용 — LUFS 정규화 포함)
    log.info("오디오 믹싱...")
    mix = producer.mix_sounds(sound_files, DURATION_LONGFORM, category=concept["category"])
    if not mix:
        return None
    audio, actual_sounds, audio_lufs, source_lufs, excluded = mix

    # Pass 1-a: 클립 1080p 정규화
    norm = temp_dir / "norm.mp4"
    if not _run([
        "ffmpeg", "-y", "-i", str(video_file),
        "-vf", (
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1"
        ),
        "-r", "24", "-c:v", "libx264", "-preset", "fast", "-crf", "28", "-an",
        str(norm),
    ], "클립 1080p 정규화"):
        return None

    # Pass 1-b: stream_loop + logo → 8h 비디오
    video_8h = temp_dir / "video_8h.mp4"
    extra_in, filter_complex, final_map = _logo_inputs_and_filter(producer)

    if filter_complex:
        cmd_loop = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(norm),
            *extra_in,
            "-filter_complex", filter_complex,
            "-map", f"[{final_map}]",
            "-t", str(DURATION_LONGFORM),
            "-c:v", "libx264", "-preset", "fast", "-crf", "28",
            "-movflags", "+faststart", "-an", str(video_8h),
        ]
    else:
        cmd_loop = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(norm),
            "-t", str(DURATION_LONGFORM),
            "-c:v", "libx264", "-preset", "fast", "-crf", "28",
            "-movflags", "+faststart", "-an", str(video_8h),
        ]

    if not _run(cmd_loop, f"Loop 8h + logo (Pass 1)"):
        return None
    producer._delete(norm)

    # Pass 2: merge (stream copy)
    safe = "".join(c for c in concept["title"][:40] if c.isalnum() or c in " _-").strip().replace(" ", "_")
    out = work_dir / f"{safe}_8h_final.mp4"
    if not _run([
        "ffmpeg", "-y",
        "-i", str(video_8h), "-i", str(audio),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart", str(out),
    ], "Video + Audio merge (Pass 2, copy)"):
        return None

    producer._delete(video_8h, audio)
    producer.cleanup_temp()

    log.info(f"롱폼 완성: {out.name} ({out.stat().st_size / 1024**3:.2f}GB)")
    return out, actual_sounds, audio_lufs, source_lufs, excluded


# ── Step 3-B: 60s 숏폼 제작 ──────────────────────────────────────────────

def produce_shorts(
    sound_files: list[Path],
    video_file: Path,
    concept: dict,
    work_dir: Path,
) -> Path | None:
    """
    독립형 60s 숏폼 (9:16, 1080x1920)
    video-only → audio-only → merge(copy) 3단계
    """
    producer = VideoProducer(work_dir)
    temp_dir = work_dir / "temp"
    temp_dir.mkdir(exist_ok=True)

    sound_src = sound_files[0] if sound_files else None
    if not sound_src or not sound_src.exists():
        log.error("숏폼 음원 없음")
        return None

    # 오디오 60s
    audio_60 = temp_dir / "audio_60s.mp3"
    if not _run([
        "ffmpeg", "-y", "-i", str(sound_src),
        "-t", str(DURATION_SHORTS),
        "-af", f"afade=t=out:st={DURATION_SHORTS - 3}:d=3",
        "-b:a", "192k", str(audio_60),
    ], "오디오 60s 컷"):
        return None

    # 비디오 60s (9:16, loop + logo)
    video_60 = temp_dir / "video_60s.mp4"
    extra_in, filter_complex, final_map = _logo_inputs_and_filter(producer)
    vf_crop = "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920"

    if filter_complex:
        # crop을 filter_complex 앞에 붙임
        fc = f"[0:v]{vf_crop}[cropped];" + filter_complex.replace("[0:v]", "[cropped]", 1)
        cmd_vid = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(video_file),
            *extra_in,
            "-filter_complex", fc,
            "-map", f"[{final_map}]",
            "-t", str(DURATION_SHORTS),
            "-c:v", "libx264", "-preset", "fast", "-crf", "28",
            "-movflags", "+faststart", "-an", str(video_60),
        ]
    else:
        cmd_vid = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(video_file),
            "-vf", vf_crop,
            "-t", str(DURATION_SHORTS),
            "-c:v", "libx264", "-preset", "fast", "-crf", "28",
            "-movflags", "+faststart", "-an", str(video_60),
        ]

    if not _run(cmd_vid, "Shorts 비디오 60s"):
        return None

    # merge
    safe = "".join(
        c for c in concept.get("shorts_title", "zen")[:30] if c.isalnum() or c in " _-"
    ).strip().replace(" ", "_") or "zen_shorts"
    out = work_dir / f"{safe}_shorts.mp4"
    if not _run([
        "ffmpeg", "-y",
        "-i", str(video_60), "-i", str(audio_60),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart", str(out),
    ], "Shorts merge"):
        return None

    producer._delete(video_60, audio_60)
    producer.cleanup_temp()

    log.info(f"숏폼 완성: {out.name} ({out.stat().st_size / 1024**2:.1f}MB)")
    return out


# ── 설명문 생성 ───────────────────────────────────────────────────────────

def _make_description(concept: dict) -> str:
    lines = [
        concept["title"],
        "",
        concept.get("description_en", ""),
        "",
        "─────────────────────────",
        "✦ Calmdromeda — 캄드로메다",
        "명상 · 요가 · 수면을 위한 8시간 힐링 음악",
        "구독하시면 새 영상을 놓치지 않아요 🔔",
        "─────────────────────────",
        "",
        " ".join(f"#{t.replace(' ','')}" for t in concept.get("tags", [])[:20]),
    ]
    return "\n".join(lines)


# ── YouTube 업로드 ────────────────────────────────────────────────────────

def upload_youtube(
    video_path: Path,
    concept: dict,
    cfg: Config,
    is_shorts: bool = False,
    hour_kst: int = 20,
    minute_kst: int = 0,
    thumbnail: Path | None = None,
) -> dict | None:
    if not cfg.upload_enabled:
        log.info("UPLOAD_ENABLED=false — 업로드 스킵")
        return None

    uploader = YouTubeUploader(
        client_secret_path=Path(cfg.youtube_client_secret_path),
        token_path=Path(cfg.youtube_token_path),
    )
    title = concept.get("shorts_title", concept["title"]) if is_shorts else concept["title"]
    if is_shorts:
        cat_tag = f"#{concept['category']}"
        title = f"{title} {cat_tag}"[:99]

    desc = "#Shorts\n\n" + _make_description(concept) if is_shorts else _make_description(concept)
    tags = concept["tags"] + (["Shorts", "유튜브쇼츠", "명상쇼츠"] if is_shorts else [])

    return uploader.upload(
        video_path=video_path,
        title=title,
        description=desc,
        tags=tags,
        thumbnail_path=thumbnail,
        language="ko",
        hour_kst=hour_kst,
        minute_kst=minute_kst,
    )


# ── 메인 ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Zen 8h 롱폼 / 숏폼 파이프라인")
    parser.add_argument("--mode", choices=["longform", "shorts", "both"], default="both",
                        help="longform=8h만 / shorts=60s만 / both=롱폼→숏폼 추출")
    parser.add_argument("--category", default=None, help="카테고리 강제 지정")
    args = parser.parse_args()

    if args.mode in ("longform", "both"):
        log.warning("=" * 60)
        log.warning("롱폼 모드: GitHub Actions 6h 제한 초과 가능 — 로컬 실행 권장")
        log.warning("=" * 60)

    cfg = Config()
    session_id = "zen_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    work_dir = cfg.output_dir / session_id
    work_dir.mkdir(parents=True, exist_ok=True)

    # 파일 로그
    log_file = work_dir / "pipeline_zen.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logging.getLogger().addHandler(fh)

    log.info(f"=== Zen Pipeline Start: {session_id} / mode={args.mode} ===")

    try:
        # 콘셉트 생성
        concept = generate_zen_concept(
            api_key=cfg.claude_api_key,
            used_assets_path=USED_ASSETS_FILE,
            force_category=args.category,
        )
        log.info(f"콘셉트: {concept['title']}")

        # 음원 수집
        sound_files = collect_audio(concept, work_dir, cfg)
        if not sound_files:
            log.error("음원 수집 실패 — 종료")
            return

        # 영상 수집
        video_file = collect_best_video(concept, work_dir, cfg)
        if not video_file:
            log.error("영상 수집 실패 — 종료")
            return

        longform_path = None
        used_sounds = sound_files
        audio_lufs = None
        source_lufs = {}
        excluded = {}

        # ── 롱폼 ────────────────────────────────────────────────────────
        if args.mode in ("longform", "both"):
            log.info("=== [롱폼] 8h 영상 제작 시작 ===")
            result = produce_longform(sound_files, video_file, concept, work_dir)
            if not result:
                log.error("롱폼 제작 실패")
                return
            longform_path, used_sounds, audio_lufs, source_lufs, excluded = result

            # 썸네일
            thumb_gen = ThumbnailGenerator(work_dir)
            thumbnail = thumb_gen.generate(
                title=concept["title"],
                category=concept["category"],
                video_path=video_file,
                title_sub=concept.get("title_sub", "8시간 명상"),
                subtitle_en=concept.get("subtitle_en", "Ancient & Calm"),
            )

            # 메타데이터
            metadata = {
                "session_id":   session_id,
                "session_type": "zen",
                "title":        concept["title"],
                "category":     concept["category"],
                "duration_hours": 8,
                "tags":         concept["tags"],
                "description":  _make_description(concept),
                "video_path":   str(longform_path),
                "thumbnail_path": str(thumbnail) if thumbnail else "",
                "created_at":   datetime.now().isoformat(),
                "used_sounds":  [f.name for f in used_sounds],
                "used_videos":  [video_file.name],
            }
            (work_dir / "metadata.json").write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            # used_assets 등록
            register_used_session(
                session_id=session_id,
                title=concept["title"],
                sound_files=used_sounds,
                video_files=[video_file],
                category=concept["category"],
                audio_lufs=audio_lufs,
                source_lufs=source_lufs,
                excluded_sources=excluded,
            )

            # 업로드 (롱폼: 다음날 20:00 KST)
            yt = upload_youtube(longform_path, concept, cfg,
                                hour_kst=20, minute_kst=0, thumbnail=thumbnail)
            if yt:
                log.info(f"롱폼 YouTube: {yt['url']} (공개: {yt['publish_at']})")

        # ── 숏폼 ────────────────────────────────────────────────────────
        if args.mode in ("shorts", "both"):
            log.info("=== [숏폼] 60s 제작 시작 ===")

            if args.mode == "both" and longform_path:
                # 롱폼에서 추출
                producer = VideoProducer(work_dir)
                shorts_path = producer.extract_shorts_clip(longform_path, duration=60)
            else:
                # 독립형 (Actions에서 실행)
                shorts_path = produce_shorts(sound_files, video_file, concept, work_dir)

            if shorts_path:
                yt_s = upload_youtube(shorts_path, concept, cfg,
                                      is_shorts=True, hour_kst=20, minute_kst=30)
                if yt_s:
                    log.info(f"숏폼 YouTube: {yt_s['url']} (공개: {yt_s['publish_at']})")
            else:
                log.warning("숏폼 제작 실패")

        log.info("=== Zen Pipeline Complete ===")

    except Exception as e:
        log.exception(f"예외 발생: {e}")
    finally:
        logging.getLogger().removeHandler(fh)
        fh.close()


if __name__ == "__main__":
    main()
