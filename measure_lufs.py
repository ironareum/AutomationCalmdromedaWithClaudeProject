"""
소스 오디오 LUFS 측정 스크립트

[사용법]
  python measure_lufs.py              # assets/sounds/ 전체 스캔
  python measure_lufs.py --used-only  # used_assets.json에 기록된 파일만

[출력]
  파일별 실제 LUFS + 3단계 판정
    ✅  -20 이상        → loudnorm 스킵 (적당)
    ⚠️  -20 ~ -24 사이  → loudnorm 적용 (안전 범위)
    ❌  -24 미만        → 제외 권장 (과도 부스트 → 왜곡 위험)
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT       = Path(__file__).parent
SOUNDS_DIR = ROOT / "assets" / "sounds"
USED_ASSETS_FILE = ROOT / "used_assets.json"
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}


def measure_lufs(file_path: Path) -> float | None:
    """ffmpeg loudnorm 분석 모드로 LUFS 측정 (인코딩 없음)"""
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        "-i", str(file_path),
        "-af", "loudnorm=I=-18:TP=-1.5:LRA=11:print_format=json",
        "-f", "null", "-"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    match = re.search(r'\{[^{}]+\}', result.stderr, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            val = data.get("input_i", "")
            if val and val not in ("-inf", "+inf"):
                return float(val)
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def collect_files(used_only: bool) -> list[Path]:
    if not SOUNDS_DIR.exists():
        print(f"[오류] 소리 폴더 없음: {SOUNDS_DIR}")
        sys.exit(1)

    if used_only:
        if not USED_ASSETS_FILE.exists():
            print(f"[오류] used_assets.json 없음: {USED_ASSETS_FILE}")
            sys.exit(1)
        data = json.loads(USED_ASSETS_FILE.read_text(encoding="utf-8"))
        used_names = set()
        for entry in data.values():
            used_names.update(entry.get("sounds", []))
        files = [f for f in SOUNDS_DIR.rglob("*")
                 if f.suffix.lower() in AUDIO_EXTS and f.name in used_names]
    else:
        files = [f for f in SOUNDS_DIR.rglob("*") if f.suffix.lower() in AUDIO_EXTS]

    return sorted(files)


def zone(lufs: float) -> tuple[str, str]:
    if lufs >= -20:
        return "safe",        "✅  적당 (loudnorm 스킵)"
    elif lufs >= -24:
        return "warn",        "⚠️  loudnorm 적용 (-20~-24)"
    else:
        return "danger",      "❌  제외 권장 (-24 미만)"


def main():
    parser = argparse.ArgumentParser(description="소스 오디오 LUFS 측정")
    parser.add_argument("--used-only", action="store_true",
                        help="used_assets.json에 기록된 파일만 측정")
    args = parser.parse_args()

    files = collect_files(args.used_only)
    if not files:
        print("측정할 오디오 파일 없음")
        return

    print(f"\n총 {len(files)}개 파일 측정 시작 (파일당 수초 소요)...\n")
    name_w = 45
    print(f"{'파일 (assets/sounds/ 기준)':<{name_w}} {'LUFS':>7}  판정")
    print("-" * (name_w + 40))

    buckets: dict[str, list[tuple[Path, float]]] = {"safe": [], "warn": [], "danger": []}
    failed: list[Path] = []

    for f in files:
        rel = str(f.relative_to(SOUNDS_DIR))
        lufs = measure_lufs(f)

        if lufs is None:
            print(f"{rel:<{name_w}} {'측정실패':>7}")
            failed.append(f)
            continue

        key, label = zone(lufs)
        buckets[key].append((f, lufs))
        print(f"{rel:<{name_w}} {lufs:>7.1f}  {label}")

    # ── 요약 ──────────────────────────────────────────────────────────────
    total = sum(len(v) for v in buckets.values())
    print("\n" + "=" * (name_w + 40))
    print(f"측정 완료: {total}개  |  실패: {len(failed)}개\n")
    print(f"  ✅  적당          {len(buckets['safe']):>3}개  (-20 LUFS 이상, loudnorm 불필요)")
    print(f"  ⚠️   loudnorm 필요 {len(buckets['warn']):>3}개  (-20 ~ -24 LUFS, 안전 범위 부스트)")
    print(f"  ❌  제외 권장     {len(buckets['danger']):>3}개  (-24 LUFS 미만, 왜곡 위험)\n")

    if buckets["danger"]:
        print("[ 제외 권장 파일 ]")
        for f, lufs in sorted(buckets["danger"], key=lambda x: x[1]):
            print(f"  {lufs:>7.1f} LUFS  {f.relative_to(SOUNDS_DIR)}")

    if buckets["warn"]:
        print("\n[ loudnorm 적용 파일 ]")
        for f, lufs in sorted(buckets["warn"], key=lambda x: x[1]):
            print(f"  {lufs:>7.1f} LUFS  {f.relative_to(SOUNDS_DIR)}")


if __name__ == "__main__":
    main()
