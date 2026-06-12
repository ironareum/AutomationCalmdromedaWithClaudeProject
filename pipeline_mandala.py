"""
만다라/프랙탈 1h 롱폼 + 40s 숏폼 파이프라인
2026.05.29 신규

실행:
  python pipeline_mandala.py --mode longform         # 1h 롱폼 (로컬 권장)
  python pipeline_mandala.py --mode shorts           # 40s 숏폼 (Actions 가능)
  python pipeline_mandala.py --mode both             # 롱폼 제작 후 숏폼 추출 (로컬)
  python pipeline_mandala.py --mode both --test      # 테스트: 3분 롱폼 + 40s 숏폼
  python pipeline_mandala.py --category mandala

[설계]
  음원: Pixabay Music only (폴백 없음, 실패 시 오류 처리)
  영상: Pexels 단일 최장 클립 (폴백 없음, 실패 시 오류 처리)
  가장 긴 트랙 우선 선택 (ffprobe로 실제 길이 측정)
  FFmpeg: normalize → loop+logo (Pass 1) → merge copy (Pass 2)
  --test: DURATION_LONGFORM을 3분(180s)으로 오버라이드
"""

import argparse
import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from collector.freesound import register_used_session, USED_ASSETS_FILE
from collector.jamendo import JamendoCollector
from collector.pexels import PexelsCollector
from config import Config
from planner.mandala_concept import generate_mandala_concept
from producer.ffmpeg_producer import VideoProducer, LOGO_PATH, LOGO_HEADING_PATH
from producer.thumbnail import ThumbnailGenerator
from uploader.youtube import YouTubeUploader

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

DURATION_LONGFORM = 1 * 3600   # 3600초
DURATION_TEST     = 3 * 60     # 180초 (테스트 모드)
DURATION_SHORTS   = 40          # 40초


# ── FFmpeg 유틸 ────────────────────────────────────────────────────────────

def _run(cmd: list, desc: str = "") -> bool:
    log.info(f"FFmpeg: {desc}")
    r = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        log.error(f"FFmpeg 실패:\n{r.stderr[-800:]}")
        return False
    return True



def _logo_inputs_and_filter(producer: VideoProducer) -> tuple[list, str, str]:
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
        parts[-1] = parts[-1].rsplit("[", 1)[0] + "[vout]"
        final = "vout"

    return extra_inputs, ";".join(parts), final


# ── Step 1: 음원 수집 (Jamendo, 가장 긴 트랙 선택) ───────────────────────

def collect_longest_music(concept: dict, work_dir: Path, cfg: Config) -> tuple[list[Path], dict | None]:
    """
    Jamendo에서 duration_desc 정렬로 가장 긴 트랙 1개 수집.
    태그: concept["jamendo_tags"], 제외: concept["jamendo_exclude"]
    실패 시 오류 로깅 후 ([], None) 반환 (폴백 없음).
    """
    if not cfg.jamendo_client_id:
        log.error("JAMENDO_CLIENT_ID 없음 — 음원 수집 불가")
        return [], None

    jc = JamendoCollector(client_id=cfg.jamendo_client_id, work_dir=work_dir, used_assets_path=USED_ASSETS_FILE)
    tags             = concept.get("jamendo_tags",            ["ambient", "newage"])
    required_vartags = concept.get("jamendo_required_vartags", ["meditative", "meditation", "calm"])
    exclude          = concept.get("jamendo_exclude",          ["piano"])

    result = jc.collect_longest(
        tags=tags,
        required_vartags=required_vartags,
        exclude_tags=exclude,
    )
    if not result:
        log.error("Jamendo 음원 수집 실패")
        return [], None

    path, track_meta = result
    return [path], track_meta


# ── Step 2: 영상 수집 (단일 최적 클립, 폴백 없음) ─────────────────────────

def collect_best_video(concept: dict, work_dir: Path, cfg: Config) -> Path | None:
    """Pexels에서 가장 긴 단일 클립 선택. 실패 시 None 반환."""
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
        if candidates:
            break

    if not candidates:
        log.error("Pexels 영상 수집 실패")
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


# ── Step 3-A: 1h 롱폼 제작 (--test 시 3분) ───────────────────────────────

def produce_longform(
    sound_files: list[Path],
    video_file: Path,
    concept: dict,
    work_dir: Path,
    duration: int = DURATION_LONGFORM,
) -> tuple | None:
    """
    2-pass 최적화:
      Pass 1: 클립 normalize → stream_loop + logo (인코딩, preset fast)
      Pass 2: video + audio merge (stream copy)
    반환: (output_path, actual_sounds, audio_lufs, source_lufs, excluded)
    """
    producer = VideoProducer(work_dir)
    temp_dir = work_dir / "temp"
    temp_dir.mkdir(exist_ok=True)

    log.info("오디오 믹싱...")
    mix = producer.mix_sounds(sound_files, duration, category=concept["category"])
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

    # Pass 1-b: stream_loop + logo
    video_loop = temp_dir / "video_loop.mp4"
    extra_in, filter_complex, final_map = _logo_inputs_and_filter(producer)

    if filter_complex:
        cmd_loop = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(norm),
            *extra_in,
            "-filter_complex", filter_complex,
            "-map", f"[{final_map}]",
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "28",
            "-movflags", "+faststart", "-an", str(video_loop),
        ]
    else:
        cmd_loop = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(norm),
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "28",
            "-movflags", "+faststart", "-an", str(video_loop),
        ]

    dur_label = f"{duration // 60}min" if duration < 3600 else f"{duration // 3600}h"
    if not _run(cmd_loop, f"Loop {dur_label} + logo (Pass 1)"):
        return None
    producer._delete(norm)

    # Pass 2: merge (stream copy)
    safe = "".join(c for c in concept["title"][:40] if c.isalnum() or c in " _-").strip().replace(" ", "_")
    out = work_dir / f"{safe}_{dur_label}_final.mp4"
    if not _run([
        "ffmpeg", "-y",
        "-i", str(video_loop), "-i", str(audio),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart", str(out),
    ], "Video + Audio merge (Pass 2, copy)"):
        return None

    producer._delete(video_loop, audio)
    producer.cleanup_temp()

    log.info(f"롱폼 완성: {out.name} ({out.stat().st_size / 1024**3:.2f}GB)")
    return out, actual_sounds, audio_lufs, source_lufs, excluded


# ── Step 3-B: 40s 숏폼 제작 ──────────────────────────────────────────────

def produce_shorts(
    sound_files: list[Path],
    video_file: Path,
    concept: dict,
    work_dir: Path,
) -> Path | None:
    """독립형 40s 숏폼 (9:16, 1080x1920)"""
    producer = VideoProducer(work_dir)
    temp_dir = work_dir / "temp"
    temp_dir.mkdir(exist_ok=True)

    sound_src = sound_files[0] if sound_files else None
    if not sound_src or not sound_src.exists():
        log.error("숏폼 음원 없음")
        return None

    # 오디오 40s
    audio_40 = temp_dir / "audio_40s.mp3"
    if not _run([
        "ffmpeg", "-y", "-i", str(sound_src),
        "-t", str(DURATION_SHORTS),
        "-af", f"afade=t=out:st={DURATION_SHORTS - 3}:d=3",
        "-b:a", "192k", str(audio_40),
    ], "오디오 40s 컷"):
        return None

    # 비디오 40s (9:16, loop + logo)
    video_40 = temp_dir / "video_40s.mp4"
    extra_in, filter_complex, final_map = _logo_inputs_and_filter(producer)
    vf_crop = "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920"

    if filter_complex:
        fc = f"[0:v]{vf_crop}[cropped];" + filter_complex.replace("[0:v]", "[cropped]", 1)
        cmd_vid = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(video_file),
            *extra_in,
            "-filter_complex", fc,
            "-map", f"[{final_map}]",
            "-t", str(DURATION_SHORTS),
            "-c:v", "libx264", "-preset", "fast", "-crf", "28",
            "-movflags", "+faststart", "-an", str(video_40),
        ]
    else:
        cmd_vid = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(video_file),
            "-vf", vf_crop,
            "-t", str(DURATION_SHORTS),
            "-c:v", "libx264", "-preset", "fast", "-crf", "28",
            "-movflags", "+faststart", "-an", str(video_40),
        ]

    if not _run(cmd_vid, "Shorts 비디오 40s"):
        return None

    # merge
    safe = "".join(
        c for c in concept.get("shorts_title", "mandala")[:30] if c.isalnum() or c in " _-"
    ).strip().replace(" ", "_") or "mandala_shorts"
    out = work_dir / f"{safe}_shorts.mp4"
    if not _run([
        "ffmpeg", "-y",
        "-i", str(video_40), "-i", str(audio_40),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart", str(out),
    ], "Shorts merge"):
        return None

    producer._delete(video_40, audio_40)
    producer.cleanup_temp()

    log.info(f"숏폼 완성: {out.name} ({out.stat().st_size / 1024**2:.1f}MB)")
    return out


# ── 설명문 생성 ───────────────────────────────────────────────────────────

def _make_description(concept: dict, jamendo_meta: dict | None = None) -> str:
    lines = [
        concept["title"],
        "",
        concept.get("description_ko", ""),
        "",
        concept.get("description_en", ""),
        "",
        "─────────────────────────",
        "✦ Calmdromeda — 캄드로메다",
        "명상 · 요가 · 수면을 위한 1시간 힐링 음악",
        "구독하시면 새 영상을 놓치지 않아요 🔔",
        "─────────────────────────",
        "",
        " ".join(f"#{t.replace(' ','')}" for t in concept.get("tags", [])[:20]),
    ]
    if jamendo_meta and jamendo_meta.get("name"):
        lines += [
            "",
            "─────────────────────────",
            f"🎵 Music: {jamendo_meta['name']} by {jamendo_meta.get('artist_name', '')}",
            f"License: {jamendo_meta.get('license_ccurl', 'https://creativecommons.org/licenses/by/3.0/')}",
            "Source: Jamendo (jamendo.com)",
            "─────────────────────────",
        ]
    return "\n".join(lines)


# ── YouTube 업로드 ────────────────────────────────────────────────────────

def upload_youtube(
    video_path: Path,
    concept: dict,
    cfg: Config,
    is_shorts: bool = False,
    hour_kst: int = 19,
    minute_kst: int = 30,
    thumbnail: Path | None = None,
    description_override: str | None = None,
    days_ahead: int = 1,
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

    if description_override:
        desc = ("#Shorts\n\n" + description_override) if is_shorts else description_override
    else:
        desc = "#Shorts\n\n" + _make_description(concept) if is_shorts else _make_description(concept)
    tags = concept["tags"] + (["Shorts", "유튜브쇼츠", "명상쇼츠"] if is_shorts else [])

    return uploader.upload(
        video_path=video_path,
        title=title,
        description=desc,
        tags=tags,
        thumbnail_path=None if is_shorts else thumbnail,  # 쇼츠는 썸네일 미설정
        language="ko",
        hour_kst=hour_kst,
        minute_kst=minute_kst,
        days_ahead=days_ahead,
    )


# ── 업로드 전용 ───────────────────────────────────────────────────────────

def _upload_only(session_dir: Path, cfg: Config):
    """기존 output 세션 폴더의 metadata.json을 읽어 업로드만 실행."""
    meta_path = session_dir / "metadata.json"
    if not meta_path.exists():
        log.error(f"metadata.json 없음: {meta_path}")
        return

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    video_path = Path(meta["video_path"])
    if not video_path.exists():
        log.error(f"영상 파일 없음: {video_path}")
        return

    thumbnail = Path(meta["thumbnail_path"]) if meta.get("thumbnail_path") else None
    concept = {
        "title":       meta["title"],
        "tags":        meta.get("tags", []),
        "category":    meta.get("category", ""),
        "shorts_title": "",
    }

    yt = upload_youtube(
        video_path=video_path,
        concept=concept,
        cfg=cfg,
        hour_kst=cfg.upload_hour_kst,
        minute_kst=cfg.upload_minute_kst,
        thumbnail=thumbnail,
        description_override=meta.get("description"),
    )
    if yt:
        log.info(f"업로드 완료: {yt['url']} (공개: {yt['publish_at']})")
    else:
        log.error("업로드 실패")


# ── 메인 ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="만다라 1h 롱폼 / 숏폼 파이프라인")
    parser.add_argument("--mode", choices=["longform", "shorts", "both"], default="both",
                        help="longform=1h만 / shorts=40s만 / both=롱폼→숏폼 추출")
    parser.add_argument("--category", default=None, help="카테고리 강제 지정")
    parser.add_argument("--test", action="store_true",
                        help="테스트 모드: 롱폼을 3분(180s)으로 생성")
    parser.add_argument("--upload-only", metavar="SESSION_DIR",
                        help="기존 output 세션 폴더 경로 → 업로드만 실행 (예: output/mandala_20260529_100000)")
    args = parser.parse_args()

    cfg = Config()

    if args.upload_only:
        _upload_only(Path(args.upload_only), cfg)
        return

    effective_duration = DURATION_TEST if args.test else DURATION_LONGFORM

    if args.mode in ("longform", "both"):
        log.warning("=" * 60)
        if args.test:
            log.warning(f"테스트 모드: {effective_duration}s({effective_duration//60}분) 영상")
        else:
            log.warning("롱폼 모드: 1시간 영상 — 로컬 실행 권장")
        log.warning("=" * 60)

    session_id = "mandala_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    work_dir = cfg.output_dir / session_id
    work_dir.mkdir(parents=True, exist_ok=True)

    log_file = work_dir / "pipeline_mandala.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logging.getLogger().addHandler(fh)

    log.info(f"=== Mandala Pipeline Start: {session_id} / mode={args.mode} / test={args.test} ===")

    try:
        # 콘셉트 생성
        concept = generate_mandala_concept(
            api_key=cfg.claude_api_key,
            used_assets_path=USED_ASSETS_FILE,
            force_category=args.category,
        )
        log.info(f"콘셉트: {concept['title']}")

        # 음원 수집
        sound_files, jamendo_meta = collect_longest_music(concept, work_dir, cfg)
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
            dur_label = f"{effective_duration//60}분" if args.test else "1시간"
            log.info(f"=== [롱폼] {dur_label} 영상 제작 시작 ===")
            result = produce_longform(sound_files, video_file, concept, work_dir,
                                      duration=effective_duration)
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
                title_sub=concept.get("title_sub", "1시간 명상"),
                subtitle_en=concept.get("subtitle_en", "Infinite Bloom"),
            )

            # 메타데이터
            desc = _make_description(concept, jamendo_meta)
            metadata = {
                "session_id":     session_id,
                "session_type":   "mandala",
                "title":          concept["title"],
                "category":       concept["category"],
                "duration_hours": round(effective_duration / 3600, 2),
                "tags":           concept["tags"],
                "description":    desc,
                "jamendo_track":  jamendo_meta or {},
                "video_path":     str(longform_path),
                "thumbnail_path": str(thumbnail) if thumbnail else "",
                "created_at":     datetime.now().isoformat(),
                "used_sounds":    [f.name for f in used_sounds],
                "used_videos":    [video_file.name],
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

            # 업로드 (롱폼: 다음날 19:30 KST)
            yt = upload_youtube(longform_path, concept, cfg,
                                hour_kst=19, minute_kst=30, thumbnail=thumbnail,
                                description_override=desc)
            if yt:
                log.info(f"롱폼 YouTube: {yt['url']} (공개: {yt['publish_at']})")

        # ── 숏폼 2개 (1/3·2/3 지점, D+1·D+2 예약) ──────────────────────
        if args.mode in ("shorts", "both") and longform_path:
            log.info("=== [숏폼] 40s × 2 제작 시작 ===")
            producer = VideoProducer(work_dir)

            # (시작초, clip_index, days_ahead)
            clips = [
                ((effective_duration * 2) // 3, 1, 2),  # 2/3 지점 → D+2
            ]
            for start_sec, clip_index, days_ahead in clips:
                sp = producer.extract_shorts_clip(
                    longform_path,
                    duration=DURATION_SHORTS,
                    start_sec=start_sec,
                    clip_index=clip_index,
                )
                if sp:
                    yt_s = upload_youtube(
                        sp, concept, cfg,
                        is_shorts=True, hour_kst=18, minute_kst=30,
                        days_ahead=days_ahead,
                        description_override=desc,
                    )
                    if yt_s:
                        log.info(f"숏폼{clip_index} YouTube: {yt_s['url']} (공개: {yt_s['publish_at']})")
                else:
                    log.warning(f"숏폼{clip_index} 제작 실패")

        log.info("=== Mandala Pipeline Complete ===")

    except Exception as e:
        log.exception(f"예외 발생: {e}")
    finally:
        logging.getLogger().removeHandler(fh)
        fh.close()


if __name__ == "__main__":
    main()
