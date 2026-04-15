#!/usr/bin/env python3
"""
음원 믹싱 테스트 스크립트
필터 설정을 바꿔가며 결과를 비교할 때 사용.

[사용법]
  # 폴더의 mp3/wav 파일로 60초 믹싱 (필터 없음)
  python test_mix.py --sounds-dir output/20260415_123456/sounds

  # 특정 프리셋으로 120초 테스트
  python test_mix.py --sounds-dir output/20260415_123456/sounds --preset normalize_only --duration 120

  # 여러 프리셋 한번에 비교 출력
  python test_mix.py --sounds-dir output/20260415_123456/sounds --all-presets

  # 커스텀 필터 직접 지정
  python test_mix.py --sounds-dir output/20260415_123456/sounds --filter "loudnorm=I=-18:TP=-2.0:LRA=11"

  # 파일 직접 지정 (순서 = main, sub, point 순)
  python test_mix.py --files a.mp3 b.mp3 c.mp3 --preset none

[프리셋 목록]
  none           : 필터 없음 (raw 믹스 그대로)
  normalize_only : loudnorm 정규화만 적용
  minimal        : highpass + lowpass + loudnorm (노이즈 제거 없음)
  original       : 최초 설정 (afftdn nf=-25, LRA=11)
  current        : 현재 설정 (afftdn + anlmdn, LRA=7)
"""

import argparse
import logging
import random
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

SOUND_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"}

PRESETS = {
    "none":           "",                                                                   # 필터 없음 (raw 믹스 그대로)
    "normalize_only": "loudnorm=I=-20:TP=-2.0:LRA=11",                                    # 정규화만 (-20 LUFS 기준)
    "minimal":        "highpass=f=40,loudnorm=I=-20:TP=-2.0:LRA=11",                      # 초저역 컷 + 정규화
    "current":        "highpass=f=80,equalizer=f=3000:t=q:w=1:g=-2",                                 # 현재 적용 설정 (loudnorm 제거)
    "prev_original":  "highpass=f=80,afftdn=nf=-25,lowpass=f=8000,loudnorm=I=-18:TP=-2.0:LRA=11",   # 이전 설정 (비교용)
}


def get_duration(path: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=10
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def run(cmd: list, label: str) -> bool:
    log.info(f"▶ {label}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log.error(f"FFmpeg 오류:\n{r.stderr[-800:]}")
        return False
    return True


def mix(
    sound_files: list[Path],
    output: Path,
    duration: int,
    af_filter: str,
    volumes: list[float] | None = None,
) -> bool:
    """
    sound_files를 믹싱하고 af_filter 적용 후 output에 저장.
    volumes: 레이어별 볼륨 [main, sub, point]. None이면 기본값 사용.
    """
    # 유효 파일만
    valid = [f for f in sound_files if f.exists() and f.suffix.lower() in SOUND_EXTENSIONS]
    if not valid:
        log.error("유효한 사운드 파일 없음")
        return False

    # duration 내림차순 정렬 → 최대 3레이어
    valid.sort(key=get_duration, reverse=True)
    layers = valid[:3]

    log.info(f"레이어 구성: {[f.name for f in layers]}")
    for f in layers:
        log.info(f"  - {f.name} ({get_duration(f):.1f}s)")

    # 볼륨 설정
    default_vols = [(0.70, 0.70), (0.20, 0.20), (0.10, 0.10)]
    if volumes is None:
        volumes = [round(random.uniform(*r), 2) for r in default_vols[:len(layers)]]
    else:
        volumes = (volumes + [0.10] * 3)[:len(layers)]
    log.info(f"볼륨: {list(zip([f.name for f in layers], volumes))}")

    raw = output.parent / f"_raw_{output.stem}.mp3"

    # ── 1단계: 믹싱 (raw) ──────────────────────────────────────────────
    if len(layers) == 1:
        cmd_mix = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(layers[0]),
            "-t", str(duration),
            "-b:a", "192k", str(raw)
        ]
    else:
        inputs = []
        for f in layers:
            inputs += ["-stream_loop", "-1", "-i", str(f)]
        amix_f = "".join(f"[{i}:a]volume={volumes[i]}[a{i}];" for i in range(len(layers)))
        mix_in = "".join(f"[a{i}]" for i in range(len(layers)))
        filter_complex = f"{amix_f}{mix_in}amix=inputs={len(layers)}:duration=longest"
        cmd_mix = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-t", str(duration),
            "-b:a", "192k", str(raw)
        ]

    if not run(cmd_mix, f"Mixing {len(layers)} layers → {duration}s raw"):
        return False

    # ── 2단계: 필터 적용 ──────────────────────────────────────────────
    fade_start = max(0, duration - 5)

    if af_filter:
        full_filter = f"{af_filter},afade=t=out:st={fade_start}:d=5"
        cmd_af = [
            "ffmpeg", "-y",
            "-i", str(raw),
            "-af", full_filter,
            "-b:a", "192k", str(output)
        ]
        ok = run(cmd_af, f"필터 적용: {af_filter}")
    else:
        # 필터 없음 — afade만
        cmd_af = [
            "ffmpeg", "-y",
            "-i", str(raw),
            "-af", f"afade=t=out:st={fade_start}:d=5",
            "-b:a", "192k", str(output)
        ]
        ok = run(cmd_af, "필터 없음 — afade만 적용")

    raw.unlink(missing_ok=True)

    if ok:
        size_mb = output.stat().st_size / (1024 * 1024)
        log.info(f"✅ 완료: {output} ({size_mb:.1f}MB)")
    return ok


def collect_sounds(sounds_dir: Path) -> list[Path]:
    files = sorted(
        [f for f in sounds_dir.iterdir() if f.suffix.lower() in SOUND_EXTENSIONS],
        key=get_duration, reverse=True
    )
    log.info(f"폴더 내 사운드 파일: {len(files)}개")
    for f in files:
        log.info(f"  {f.name} ({get_duration(f):.1f}s)")
    return files


def main():
    parser = argparse.ArgumentParser(
        description="음원 믹싱 테스트 — 필터 설정 비교용",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    src_group = parser.add_mutually_exclusive_group(required=True)
    src_group.add_argument("--sounds-dir", type=Path,
                           help="사운드 폴더 경로 (mp3/wav 자동 수집)")
    src_group.add_argument("--files", type=Path, nargs="+",
                           help="사운드 파일 직접 지정 (main sub point 순)")

    parser.add_argument("--preset", choices=list(PRESETS.keys()), default="none",
                        help=f"필터 프리셋 (기본: none). 선택: {list(PRESETS.keys())}")
    parser.add_argument("--all-presets", action="store_true",
                        help="모든 프리셋으로 각각 출력 파일 생성")
    parser.add_argument("--filter", dest="custom_filter", default=None,
                        help="커스텀 FFmpeg af 필터 문자열 (--preset 무시됨)")
    parser.add_argument("--duration", type=int, default=60,
                        help="테스트 길이 (초, 기본 60)")
    parser.add_argument("--volumes", type=float, nargs="+",
                        help="레이어별 볼륨 (예: 0.7 0.2 0.1)")
    parser.add_argument("--out-dir", type=Path, default=Path("test_output"),
                        help="출력 폴더 (기본: ./test_output)")

    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    # 소스 파일 수집
    if args.sounds_dir:
        if not args.sounds_dir.exists():
            log.error(f"폴더 없음: {args.sounds_dir}")
            sys.exit(1)
        sound_files = collect_sounds(args.sounds_dir)
    else:
        sound_files = args.files

    if not sound_files:
        log.error("사운드 파일 없음")
        sys.exit(1)

    # 실행
    if args.all_presets:
        log.info(f"\n{'='*60}")
        log.info(f"전체 프리셋 비교 테스트 ({args.duration}초)")
        log.info(f"{'='*60}")
        for name, af in PRESETS.items():
            out = args.out_dir / f"mix_{name}_{args.duration}s.mp3"
            log.info(f"\n[{name}] 필터: {af or '(없음)'}")
            mix(sound_files, out, args.duration, af, args.volumes)
        log.info(f"\n완료. 출력 폴더: {args.out_dir.resolve()}")

    else:
        if args.custom_filter is not None:
            af = args.custom_filter
            label = "custom"
        else:
            af = PRESETS[args.preset]
            label = args.preset

        out = args.out_dir / f"mix_{label}_{args.duration}s.mp3"
        log.info(f"프리셋: [{label}]  필터: {af or '(없음)'}")
        ok = mix(sound_files, out, args.duration, af, args.volumes)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
