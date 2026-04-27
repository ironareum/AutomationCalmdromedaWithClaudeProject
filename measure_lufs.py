"""
소스 오디오 LUFS 측정 스크립트

[사용법]
  python measure_lufs.py              # assets/sounds/ 전체 스캔 (파일 직접 측정)
  python measure_lufs.py --used-only  # used_assets.json에 기록된 LUFS 이력만 출력

[--used-only 주의]
  PR #25 merge 이후 세션부터 source_lufs / audio_lufs 데이터가 기록됩니다.
  이전 세션은 "LUFS 미기록" 으로 표시됩니다.

[출력 판정 기준]
  ✅  -20 이상        → loudnorm 스킵 (적당)
  ⚠️  -20 ~ -24 사이  → loudnorm 적용 (안전 범위)
  ❌  -24 미만        → 제외 권장 (왜곡 위험)
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT             = Path(__file__).parent
SOUNDS_DIR       = ROOT / "assets" / "sounds"
USED_ASSETS_FILE = ROOT / "used_assets.json"
AUDIO_EXTS       = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}


def zone(lufs: float) -> str:
    if lufs >= -20:
        return "✅  적당"
    elif lufs >= -24:
        return "⚠️  loudnorm 적용"
    else:
        return "❌  제외 권장"


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
                return round(float(val), 1)
        except (json.JSONDecodeError, ValueError):
            pass
    return None


# ── --used-only: used_assets.json 기록 데이터만 출력 ──────────────────────

def run_used_only():
    if not USED_ASSETS_FILE.exists():
        print(f"[오류] used_assets.json 없음: {USED_ASSETS_FILE}")
        sys.exit(1)

    data = json.loads(USED_ASSETS_FILE.read_text(encoding="utf-8"))
    if not data:
        print("used_assets.json에 데이터 없음")
        return

    buckets = {"safe": [], "warn": [], "danger": []}
    no_record_sessions = []

    for session_id, entry in sorted(data.items()):
        title         = entry.get("title", session_id)
        sounds        = entry.get("sounds", [])
        source_lufs   = entry.get("source_lufs", {})
        audio_lufs    = entry.get("audio_lufs")
        excluded      = entry.get("excluded_sources", {})
        quality       = entry.get("quality", "pending")

        has_lufs_data = bool(source_lufs) or audio_lufs is not None

        mix_str = f"믹스 {audio_lufs} LUFS" if audio_lufs is not None else "믹스 LUFS 미기록"
        print(f"\n▶ [{session_id}] {title}  ({quality})  |  {mix_str}")

        if not has_lufs_data:
            print(f"  → LUFS 미기록 (PR #25 이전 세션, 파일은 이미 삭제됨)")
            no_record_sessions.append(session_id)
            continue

        # 소스별 LUFS 출력
        name_w = 40
        for filename in sounds:
            lufs = source_lufs.get(filename)
            if lufs is None:
                print(f"  {filename:<{name_w}} 측정값 없음")
                continue
            label = zone(lufs)
            print(f"  {filename:<{name_w}} {lufs:>7.1f}  {label}")
            if lufs >= -20:
                buckets["safe"].append((filename, lufs))
            elif lufs >= -24:
                buckets["warn"].append((filename, lufs))
            else:
                buckets["danger"].append((filename, lufs))

        # 자동 제외된 파일
        for fname, lufs in excluded.items():
            print(f"  {fname:<{name_w}} {lufs:>7.1f}  ❌  파이프라인 자동 제외")
            buckets["danger"].append((fname, lufs))

    # ── 요약 ──────────────────────────────────────────────────────────────
    total = sum(len(v) for v in buckets.values())
    print("\n" + "=" * 70)
    print(f"LUFS 기록 세션: {len(data) - len(no_record_sessions)}개  "
          f"|  미기록(이전) 세션: {len(no_record_sessions)}개\n")
    print(f"  ✅  적당          {len(buckets['safe']):>3}개  (-20 LUFS 이상)")
    print(f"  ⚠️   loudnorm 필요 {len(buckets['warn']):>3}개  (-20 ~ -24 LUFS)")
    print(f"  ❌  제외 권장     {len(buckets['danger']):>3}개  (-24 LUFS 미만)\n")

    if buckets["danger"]:
        print("[ 제외 권장 / 자동 제외된 파일 ]")
        for name, lufs in sorted(buckets["danger"], key=lambda x: x[1]):
            print(f"  {lufs:>7.1f} LUFS  {name}")


# ── 전체 스캔: assets/sounds/ 직접 측정 ──────────────────────────────────

def run_full_scan():
    if not SOUNDS_DIR.exists():
        print(f"[오류] 소리 폴더 없음: {SOUNDS_DIR}")
        sys.exit(1)

    files = sorted(f for f in SOUNDS_DIR.rglob("*") if f.suffix.lower() in AUDIO_EXTS)
    if not files:
        print("측정할 오디오 파일 없음")
        return

    name_w = 45
    print(f"\n총 {len(files)}개 파일 측정 시작...\n")
    print(f"{'파일 (assets/sounds/ 기준)':<{name_w}} {'LUFS':>7}  판정")
    print("-" * (name_w + 40))

    buckets = {"safe": [], "warn": [], "danger": []}
    failed = []

    for f in files:
        rel  = str(f.relative_to(SOUNDS_DIR))
        lufs = measure_lufs(f)
        if lufs is None:
            print(f"{rel:<{name_w}} {'측정실패':>7}")
            failed.append(rel)
            continue
        label = zone(lufs)
        print(f"{rel:<{name_w}} {lufs:>7.1f}  {label}")
        if lufs >= -20:
            buckets["safe"].append((rel, lufs))
        elif lufs >= -24:
            buckets["warn"].append((rel, lufs))
        else:
            buckets["danger"].append((rel, lufs))

    total = sum(len(v) for v in buckets.values())
    print("\n" + "=" * (name_w + 40))
    print(f"측정 완료: {total}개  |  실패: {len(failed)}개\n")
    print(f"  ✅  적당          {len(buckets['safe']):>3}개")
    print(f"  ⚠️   loudnorm 필요 {len(buckets['warn']):>3}개")
    print(f"  ❌  제외 권장     {len(buckets['danger']):>3}개\n")

    if buckets["danger"]:
        print("[ 제외 권장 파일 ]")
        for name, lufs in sorted(buckets["danger"], key=lambda x: x[1]):
            print(f"  {lufs:>7.1f} LUFS  {name}")


# ── 진입점 ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="소스 오디오 LUFS 측정/확인")
    parser.add_argument("--used-only", action="store_true",
                        help="used_assets.json에 기록된 LUFS 이력만 출력 (파일 탐색 없음)")
    args = parser.parse_args()

    if args.used_only:
        run_used_only()
    else:
        run_full_scan()


if __name__ == "__main__":
    main()
