"""
우주/코스믹 1h 롱폼 + 15s 숏폼 파이프라인
2026.06.24 신규

실행:
  python pipeline_cosmic.py --mode longform         # 1h 롱폼 (로컬 권장)
  python pipeline_cosmic.py --mode shorts           # 15s 숏폼
  python pipeline_cosmic.py --mode both             # 롱폼 제작 후 숏폼 추출 (로컬)
  python pipeline_cosmic.py --mode both --test      # 테스트: 3분 롱폼 + 15s 숏폼
  python pipeline_cosmic.py --category galaxy

[설계]
  채널 컨셉: Calm(잠) + Andromeda(우주) — 잠과 우주
  음원: Jamendo ambient/atmospheric (폴백 없음, 실패 시 오류 처리)
  영상: Pexels 우주/은하/오로라/성운 단일 최장 클립
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
from planner.cosmic_concept import generate_cosmic_concept
from producer.ffmpeg_producer import VideoProducer, LOGO_PATH, LOGO_HEADING_PATH
from producer.ffmpeg_cosmic import CosmicProducer
from producer.thumbnail import ThumbnailGenerator
from producer.thumbnail_cosmic import CosmicThumbnailGenerator
from uploader.youtube import YouTubeUploader

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

DURATION_LONGFORM = 1 * 3600   # 3600초
DURATION_TEST     = 3 * 60     # 180초 (테스트 모드)
DURATION_SHORTS   = 15         # 15초

# ── 버전 상수 ─────────────────────────────────────────────────────────────
BLUEPRINT_VERSION      = "1.0"
PIPELINE_VERSION       = "cosmic-v1"
PROMPT_VERSION         = "1.0"
BOTH_MODE_SHORTS_DELAY = 1    # both 모드: 숏폼을 롱폼보다 하루 늦게 공개


# ── 시리즈 카운트 헬퍼 ────────────────────────────────────────────────────

def _get_longform_series_count(used_assets_path: Path) -> int:
    """현재 longform 시리즈 카운트 반환 (없으면 0)"""
    if not used_assets_path.exists():
        return 0
    try:
        data = json.loads(used_assets_path.read_text(encoding="utf-8"))
        return data.get("series", {}).get("longform", 0)
    except Exception:
        return 0


def _increment_longform_series_count(used_assets_path: Path) -> int:
    """longform 시리즈 카운트 +1 저장, 새 값 반환"""
    try:
        data = {}
        if used_assets_path.exists():
            data = json.loads(used_assets_path.read_text(encoding="utf-8"))
        series = data.get("series", {"longform": 0, "shorts": 0})
        series.setdefault("longform", 0)
        series.setdefault("shorts", 0)
        series["longform"] += 1
        data["series"] = series
        used_assets_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return series["longform"]
    except Exception as e:
        log.warning(f"시리즈 카운트 저장 실패: {e}")
        return 0


# ── 메타데이터 빌더 ───────────────────────────────────────────────────────

def _build_metadata(
    session_id: str,
    concept: dict,
    series_num: int,
    effective_duration: int,
    desc: str,
    longform_path: Path,
    thumbnail: Path | None,
    video_file: Path,
    used_sounds: list[Path],
    jamendo_meta: dict | None,
    audio_lufs: float | None,
    source_lufs: dict,
    excluded: dict,
) -> dict:
    return {
        "session_id":        session_id,
        "session_type":      "cosmic",
        "blueprint_version": BLUEPRINT_VERSION,
        "pipeline_version":  PIPELINE_VERSION,
        "prompt_version":    PROMPT_VERSION,
        "title":             concept["title"],
        "category":          concept["category"],
        "subconcept_id":     concept.get("subconcept_id", ""),
        "subconcept_en":     concept.get("subconcept_en", ""),
        "subconcept_ko":     concept.get("subconcept_ko", ""),
        "series":            {"longform": series_num, "shorts": 0},
        "duration_hours":    round(effective_duration / 3600, 2),
        "tags":              concept["tags"],
        "description":       desc,
        "jamendo_track":     jamendo_meta or {},
        "video_path":        str(longform_path),
        "thumbnail_path":    str(thumbnail) if thumbnail else "",
        "shorts_overlay_text": concept.get("description_ko", ""),
        "created_at":        datetime.now().isoformat(),
        "used_sounds":       [f.name for f in used_sounds],
        "used_videos":       [video_file.name],
        "audio_lufs":        audio_lufs,
        "source_lufs":       source_lufs or {},
        "excluded_sources":  excluded or {},
    }


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


def _logo_inputs_and_filter_cosmic(producer: VideoProducer) -> tuple[list, str, str]:
    """코스믹 파이프라인 전용: 우하단 원형 로고만 (좌상단 헤딩 로고 제외)"""
    if not LOGO_PATH.exists():
        return [], "", "0:v"

    extra_inputs = ["-i", str(LOGO_PATH)]
    filter_complex = (
        "[1:v]scale=180:-2,format=rgba,colorchannelmixer=aa=0.6[lc];"
        "[0:v][lc]overlay=W-w-20:H-h-20[vout]"
    )
    return extra_inputs, filter_complex, "vout"


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
    tags             = concept.get("jamendo_tags",            ["ambient", "atmospheric"])
    required_vartags = concept.get("jamendo_required_vartags", ["meditative", "meditation", "calm", "dreamy"])
    exclude          = concept.get("jamendo_exclude",          ["piano", "upbeat", "dance", "pop", "rock", "jazz"])

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
    producer = CosmicProducer(work_dir)
    temp_dir = work_dir / "temp"
    temp_dir.mkdir(exist_ok=True)

    log.info("오디오 믹싱 (Jamendo 음악 전용, loudnorm 없음)...")
    mix = producer.mix_sounds_music(sound_files, duration)
    if not mix:
        return None
    audio, actual_sounds, audio_lufs, source_lufs, excluded = mix

    # Pass 1-a: 클립 1080p 정규화 (crop 방식 — 검은 여백 없이 꽉 채워서 자르기)
    norm = temp_dir / "norm.mp4"
    if not _run([
        "ffmpeg", "-y", "-i", str(video_file),
        "-vf", (
            "scale=1920:1080:force_original_aspect_ratio=increase,"
            "crop=1920:1080,setsar=1"
        ),
        "-r", "24", "-c:v", "libx264", "-preset", "fast", "-crf", "28", "-an",
        str(norm),
    ], "클립 1080p 정규화"):
        return None

    # Pass 1-b: loop 필터 + logo (stream_loop PTS 불연속 → loop 필터로 대체)
    video_loop = temp_dir / "video_loop.mp4"
    extra_in, filter_complex, final_map = _logo_inputs_and_filter_cosmic(producer)

    dur_label = f"{duration // 60}min" if duration < 3600 else f"{duration // 3600}h"
    frame_count = producer._get_frame_count(norm)
    concat_f = None  # fallback용

    if frame_count and filter_complex:
        # loop 필터를 filter_complex 앞에 삽입 + 로고 overlay
        fc_with_loop = (
            f"[0:v]loop=-1:size={frame_count}:start=0[vloop];"
            + filter_complex.replace("[0:v]", "[vloop]")
        )
        cmd_loop = [
            "ffmpeg", "-y",
            "-i", str(norm),
            *extra_in,
            "-filter_complex", fc_with_loop,
            "-map", f"[{final_map}]",
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "28",
            "-movflags", "+faststart", "-an", str(video_loop),
        ]
    elif frame_count:
        # loop 필터 (로고 없음)
        cmd_loop = [
            "ffmpeg", "-y",
            "-i", str(norm),
            "-vf", f"loop=-1:size={frame_count}:start=0",
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "28",
            "-movflags", "+faststart", "-an", str(video_loop),
        ]
    else:
        # fallback: concat demuxer (프레임 수 조회 실패 시)
        log.warning("프레임 수 조회 실패 — concat demuxer fallback")
        norm_dur = producer.get_duration(norm)
        repeat = max(1, int(duration / max(norm_dur, 1)) + 2)
        concat_f = temp_dir / "concat_loop.txt"
        with open(concat_f, "w") as fp:
            for _ in range(repeat):
                fp.write(f"file '{norm.resolve()}'\n")
        if filter_complex:
            cmd_loop = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", str(concat_f),
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
                "-f", "concat", "-safe", "0", "-i", str(concat_f),
                "-t", str(duration),
                "-c:v", "libx264", "-preset", "fast", "-crf", "28",
                "-movflags", "+faststart", "-an", str(video_loop),
            ]

    if not _run(cmd_loop, f"Loop {dur_label} + logo (Pass 1)"):
        return None
    producer._delete(norm)
    if concat_f:
        producer._delete(concat_f)

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


# ── Step 3-B: 15s 숏폼 제작 ──────────────────────────────────────────────

def produce_shorts(
    sound_files: list[Path],
    video_file: Path,
    concept: dict,
    work_dir: Path,
) -> Path | None:
    """독립형 15s 숏폼 (9:16, 1080x1920)"""
    producer = VideoProducer(work_dir)
    temp_dir = work_dir / "temp"
    temp_dir.mkdir(exist_ok=True)

    sound_src = sound_files[0] if sound_files else None
    if not sound_src or not sound_src.exists():
        log.error("숏폼 음원 없음")
        return None

    # 오디오 15s
    audio_15 = temp_dir / "audio_15s.mp3"
    if not _run([
        "ffmpeg", "-y", "-i", str(sound_src),
        "-t", str(DURATION_SHORTS),
        "-af", f"afade=t=out:st={DURATION_SHORTS - 3}:d=3",
        "-b:a", "192k", str(audio_15),
    ], "오디오 15s 컷"):
        return None

    # 비디오 15s (9:16, loop + logo)
    video_15 = temp_dir / "video_15s.mp4"
    extra_in, filter_complex, final_map = _logo_inputs_and_filter_cosmic(producer)
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
            "-movflags", "+faststart", "-an", str(video_15),
        ]
    else:
        cmd_vid = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(video_file),
            "-vf", vf_crop,
            "-t", str(DURATION_SHORTS),
            "-c:v", "libx264", "-preset", "fast", "-crf", "28",
            "-movflags", "+faststart", "-an", str(video_15),
        ]

    if not _run(cmd_vid, "Shorts 비디오 15s"):
        return None

    # merge
    safe = "".join(
        c for c in concept.get("shorts_title", "cosmic")[:30] if c.isalnum() or c in " _-"
    ).strip().replace(" ", "_") or "cosmic_shorts"
    out = work_dir / f"{safe}_shorts.mp4"
    if not _run([
        "ffmpeg", "-y",
        "-i", str(video_15), "-i", str(audio_15),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart", str(out),
    ], "Shorts merge"):
        return None

    producer._delete(video_15, audio_15)
    producer.cleanup_temp()

    log.info(f"숏폼 완성: {out.name} ({out.stat().st_size / 1024**2:.1f}MB)")
    return out


# ── 설명문 생성 ───────────────────────────────────────────────────────────

def _wrap_text_to_width(text: str, font, draw, max_width: int) -> list[str]:
    """공백 기준으로 단어를 쌓다가 폭 초과 시 줄바꿈"""
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if (bbox[2] - bbox[0]) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _overlay_intro_text(clip_path: Path, intro_text: str, work_dir: Path) -> Path | None:
    """Pillow로 문장 자동 줄바꿈 텍스트 블록 PNG 1장 생성 + FFmpeg overlay
    fade-in 1s → hold → fade-out 1s (총 15s 기준, out 시작 st=13)
    """
    from PIL import Image, ImageDraw, ImageFont

    sentences = [s.strip() for s in intro_text.replace("\n", " ").split(". ") if s.strip()]
    sentences = [s if s.endswith(".") else f"{s}." for s in sentences]
    if not sentences:
        return clip_path

    font_path = Path(__file__).parent / "assets" / "fonts" / "NanumMyeongjo.ttf"
    if not font_path.exists():
        log.warning("나눔명조 폰트 없음 — 텍스트 오버레이 스킵")
        return clip_path

    W, H = 1080, 1920
    max_w = int(W * 0.84)
    line_gap = 12

    img_dummy = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_dummy = ImageDraw.Draw(img_dummy)

    # 폰트 크기 44→28까지 줄이며 6줄 이내로 맞는 크기 탐색
    font_size = 28
    lines: list[str] = []
    for size in range(44, 27, -2):
        try:
            fnt = ImageFont.truetype(str(font_path), size)
        except Exception as e:
            log.warning(f"폰트 로드 실패 — 스킵: {e}")
            return clip_path
        wrapped = []
        for s in sentences:
            wrapped += _wrap_text_to_width(s, fnt, draw_dummy, max_w)
        if len(wrapped) <= 6:
            font_size = size
            lines = wrapped
            break
    if not lines:
        font_size = 28
        fnt = ImageFont.truetype(str(font_path), font_size)
        for s in sentences:
            lines += _wrap_text_to_width(s, fnt, draw_dummy, max_w)
        lines = lines[:6]

    font = ImageFont.truetype(str(font_path), font_size)

    line_heights = []
    for line in lines:
        bbox = draw_dummy.textbbox((0, 0), line, font=font)
        line_heights.append(bbox[3] - bbox[1])
    total_h = sum(line_heights) + line_gap * (len(lines) - 1)

    # 블록 세로 중앙 기준 (화면 40% 위치)
    block_top = int(H * 0.40) - total_h // 2

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    y = block_top
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (W - tw) // 2
        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 160))
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_heights[i] + line_gap

    png_path = work_dir / "_intro_text_block.png"
    img.save(str(png_path))

    # fade-in 1s → hold → fade-out 1s (st=13 → out 완료 at 14s, 여유 1s)
    fc = (
        "[1:v]format=rgba,"
        "fade=t=in:st=0:d=1:alpha=1,"
        "fade=t=out:st=13:d=1:alpha=1[txt];"
        "[0:v][txt]overlay=0:0[vout]"
    )

    out = work_dir / (clip_path.stem + "_intro.mp4")
    ok = _run([
        "ffmpeg", "-y",
        "-i", str(clip_path),
        "-loop", "1", "-i", str(png_path),
        "-filter_complex", fc,
        "-map", "[vout]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "copy", "-t", "15",
        str(out),
    ], "쇼츠 인트로 텍스트 오버레이 (블록 fade)")

    try:
        png_path.unlink()
    except Exception:
        pass

    if ok and out.exists():
        try:
            clip_path.unlink()
        except Exception:
            pass
        return out
    return clip_path


def _make_description(concept: dict, jamendo_meta: dict | None = None) -> str:
    lines = [
        ".\n".join(s.strip() for s in concept.get("description_ko", "").split(". ") if s.strip()),
        "",
        "─────────────────────────",
        "✦ Calmdromeda — 캄드로메다",
        "우주 수면음악 채널 | 잠들기 위한 1시간",
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


def _make_shorts_description(concept: dict, jamendo_meta: dict | None = None) -> str:
    """쇼츠 전용 설명 — 정보성 고정 문구 + Jamendo 크레딧"""
    lines = [
        "🌙 Calmdromeda — 우주에서 잠드는 경험",
        "이어폰보다는 스피커로, 볼륨은 낮게 틀어두고 잠들어보세요.",
        "구독하면 매일 새로운 우주 사운드를 만나실 수 있어요.",
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
    minute_kst: int = 45,
    thumbnail: Path | None = None,
    description_override: str | None = None,
    days_ahead: int = 2,
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
    tags = concept["tags"] + (["Shorts", "유튜브쇼츠", "수면쇼츠"] if is_shorts else [])

    return uploader.upload(
        video_path=video_path,
        title=title,
        description=desc,
        tags=tags,
        thumbnail_path=None if is_shorts else thumbnail,
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
        "title":        meta["title"],
        "tags":         meta.get("tags", []),
        "category":     meta.get("category", ""),
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
    parser = argparse.ArgumentParser(description="코스믹 1h 롱폼 / 숏폼 파이프라인")
    parser.add_argument("--mode", choices=["longform", "shorts", "both"], default="both",
                        help="longform=1h만 / shorts=15s만 / both=롱폼→숏폼 추출")
    parser.add_argument("--category", default=None,
                        help="카테고리 강제 지정 (galaxy/aurora/stellar/nebula)")
    parser.add_argument("--test", action="store_true",
                        help="테스트 모드: 롱폼을 3분(180s)으로 생성")
    parser.add_argument("--upload-only", metavar="SESSION_DIR",
                        help="기존 output 세션 폴더 경로 → 업로드만 실행 (예: output/cosmic_20260624_100000)")
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

    session_id = "cosmic_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    work_dir = cfg.output_dir / session_id
    work_dir.mkdir(parents=True, exist_ok=True)

    log_file = work_dir / "pipeline_cosmic.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logging.getLogger().addHandler(fh)

    log.info(f"=== Cosmic Pipeline Start: {session_id} / mode={args.mode} / test={args.test} ===")

    try:
        # ── Collect Phase ────────────────────────────────────────────────
        log.info("=== Collect Phase ===")

        concept = generate_cosmic_concept(
            api_key=cfg.claude_api_key,
            used_assets_path=USED_ASSETS_FILE,
            force_category=args.category,
        )
        log.info(f"콘셉트: {concept['title']}")

        sound_files, jamendo_meta = collect_longest_music(concept, work_dir, cfg)
        if not sound_files:
            log.error("음원 수집 실패 — 종료")
            return

        video_file = collect_best_video(concept, work_dir, cfg)
        if not video_file:
            log.error("영상 수집 실패 — 종료")
            return

        # ── 초기화 ──────────────────────────────────────────────────────
        longform_path = None
        used_sounds   = sound_files
        audio_lufs    = None
        source_lufs   = {}
        excluded      = {}

        # ── Produce Phase ────────────────────────────────────────────────
        log.info("=== Produce Phase ===")

        if args.mode in ("longform", "both"):
            dur_label = f"{effective_duration//60}분" if args.test else "1시간"
            log.info(f"[롱폼] {dur_label} 영상 제작 시작")
            result = produce_longform(sound_files, video_file, concept, work_dir,
                                      duration=effective_duration)
            if not result:
                log.error("롱폼 제작 실패")
                return
            longform_path, used_sounds, audio_lufs, source_lufs, excluded = result

            series_num = _get_longform_series_count(USED_ASSETS_FILE) + 1
            log.info(
                f"콘셉트 확정: {concept['category'].upper()}"
                f" → {concept['subconcept_en']}"
                f" → Space Journey #{series_num:03d}"
            )

            thumb_gen = CosmicThumbnailGenerator(work_dir)
            thumbnail = thumb_gen.generate(
                video_path=video_file,
                emotion_copy=concept.get("longform_emotional", ""),
            )

            desc = _make_description(concept, jamendo_meta)
            metadata = _build_metadata(
                session_id=session_id,
                concept=concept,
                series_num=series_num,
                effective_duration=effective_duration,
                desc=desc,
                longform_path=longform_path,
                thumbnail=thumbnail,
                video_file=video_file,
                used_sounds=used_sounds,
                jamendo_meta=jamendo_meta,
                audio_lufs=audio_lufs,
                source_lufs=source_lufs,
                excluded=excluded,
            )
            (work_dir / "metadata.json").write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
            )

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

            _increment_longform_series_count(USED_ASSETS_FILE)
            log.info(f"Space Journey #{series_num:03d} — 시리즈 카운트 저장")

            # ── Upload Phase ─────────────────────────────────────────────
            log.info("=== Upload Phase ===")
            yt = upload_youtube(longform_path, concept, cfg,
                                hour_kst=cfg.upload_hour_kst, minute_kst=cfg.upload_minute_kst,
                                thumbnail=thumbnail, days_ahead=cfg.upload_days_ahead,
                                description_override=desc)
            if yt:
                log.info(f"롱폼 YouTube: {yt['url']} (공개: {yt['publish_at']})")

        # ── 숏폼 단독 모드 (--mode shorts) ───────────────────────────────
        if args.mode == "shorts":
            log.info("=== Produce Phase ===")
            log.info("[숏폼 단독] 15s 제작 시작")
            shorts_path = produce_shorts(sound_files, video_file, concept, work_dir)
            if shorts_path:
                intro = concept.get("description_ko", "")
                if intro:
                    shorts_path = _overlay_intro_text(shorts_path, intro, work_dir) or shorts_path
                desc_s = _make_shorts_description(concept, jamendo_meta)
                log.info("=== Upload Phase ===")
                yt_s = upload_youtube(
                    shorts_path, concept, cfg,
                    is_shorts=True,
                    hour_kst=cfg.shorts_upload_hour_kst,
                    minute_kst=cfg.shorts_upload_minute_kst,
                    days_ahead=cfg.upload_days_ahead,
                    description_override=desc_s,
                )
                if yt_s:
                    log.info(f"숏폼 YouTube: {yt_s['url']} (공개: {yt_s['publish_at']})")
            else:
                log.warning("숏폼 제작 실패")
            # 음원 이력 미등록 — 롱폼 dedup 풀 보존
            register_used_session(
                session_id=session_id,
                title=concept.get("shorts_title", concept["title"]),
                sound_files=[],
                video_files=[video_file],
                category=concept["category"],
            )

        # ── both 모드 숏폼 (롱폼에서 추출, D+UPLOAD_DAYS_AHEAD+BOTH_MODE_SHORTS_DELAY 예약) ──
        if args.mode == "both" and longform_path:
            log.info("[숏폼] 15s 제작 시작")
            producer = VideoProducer(work_dir)

            start_sec = 0
            sp = producer.extract_shorts_clip(
                longform_path,
                duration=DURATION_SHORTS,
                start_sec=start_sec,
                clip_index=1,
            )
            if sp:
                intro = concept.get("description_ko", "")
                if intro:
                    sp = _overlay_intro_text(sp, intro, work_dir) or sp
                desc_shorts = _make_shorts_description(concept, jamendo_meta)
                yt_s = upload_youtube(
                    sp, concept, cfg,
                    is_shorts=True,
                    hour_kst=cfg.shorts_upload_hour_kst,
                    minute_kst=cfg.shorts_upload_minute_kst,
                    days_ahead=cfg.upload_days_ahead + BOTH_MODE_SHORTS_DELAY,
                    description_override=desc_shorts,
                )
                if yt_s:
                    log.info(f"숏폼 YouTube: {yt_s['url']} (공개: {yt_s['publish_at']})")
            else:
                log.warning("숏폼 제작 실패")

        log.info("=== Cosmic Pipeline Complete ===")

    except Exception as e:
        log.exception(f"예외 발생: {e}")
    finally:
        logging.getLogger().removeHandler(fh)
        fh.close()


if __name__ == "__main__":
    main()
