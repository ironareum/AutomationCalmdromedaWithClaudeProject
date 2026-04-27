"""
소스 오디오 LUFS 측정 스크립트

[사용법]
  python measure_lufs.py              # assets/sounds/ 전체 스캔
  python measure_lufs.py --used-only  # used_assets.json 기록 기반 측정

[--used-only 동작]
  1. used_assets.json의 source_lufs 데이터가 이미 있으면 → 재측정 없이 바로 출력
  2. 데이터가 없으면 → output/{session_id}/sounds/ 와 assets/sounds/_used/ 에서 파일 탐색 후 측정

[출력]
  파일별 실제 LUFS + 3단계 판정
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
OUTPUT_DIR       = ROOT / "output"
USED_ASSETS_FILE = ROOT / "used_assets.json"
AUDIO_EXTS       = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}


# ── LUFS 측정 ──────────────────────────────────────────────────────────────

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


def zone(lufs: float) -> str:
    if lufs >= -20:
        return "✅  적당 (loudnorm 스킵)"
    elif lufs >= -24:
        return "⚠️  loudnorm 적용 (-20~-24)"
    else:
        return "❌  제외 권장 (-24 미만)"


# ── 파일 탐색 ──────────────────────────────────────────────────────────────

def find_file(filename: str, session_id: str) -> Path | None:
    """파일명을 session output 폴더 → assets/_used 순으로 탐색"""
    candidates = [
        OUTPUT_DIR / session_id / "sounds" / filename,
        SOUNDS_DIR / "_used" / session_id / filename,
    ]
    # 날짜 prefix 폴더 대응 (session_id가 YYYYMMDD_HHMMSS 형식일 때)
    date_prefix = session_id[:8] if len(session_id) >= 8 else ""
    if date_prefix:
        candidates.append(SOUNDS_DIR / "_used" / date_prefix / filename)

    for path in candidates:
        if path.exists():
            return path
    return None


# ── 모드별 실행 ────────────────────────────────────────────────────────────

def run_used_only():
    if not USED_ASSETS_FILE.exists():
        print(f"[오류] used_assets.json 없음: {USED_ASSETS_FILE}")
        sys.exit(1)

    data = json.loads(USED_ASSETS_FILE.read_text(encoding="utf-8"))
    if not data:
        print("used_assets.json에 데이터 없음")
        return

    name_w = 40
    print(f"\n{'파일명':<{name_w}} {'LUFS':>7}  {'판정'}")
    print("-" * (name_w + 45))

    buckets = {"safe": [], "warn": [], "danger": []}
    no_data, not_found, failed = [], [], []

    for session_id, entry in sorted(data.items()):
        title    = entry.get("title", session_id)
        sounds   = entry.get("sounds", [])
        recorded = entry.get("source_lufs", {})  # 파이프라인이 이미 기록한 데이터

        print(f"\n▶ [{session_id}] {title}")

        for filename in sounds:
            if filename in recorded and recorded[filename] is not None:
                # 이미 기록된 LUFS 데이터 사용 (재측정 불필요)
                lufs = recorded[filename]
                label = zone(lufs)
                print(f"  {filename:<{name_w}} {lufs:>7.1f}  {label}  (기록됨)")
                _bucket(buckets, filename, lufs)

            else:
                # 파일 탐색 후 실측
                path = find_file(filename, session_id)
                if path is None:
                    print(f"  {filename:<{name_w}} {'파일없음':>7}")
                    not_found.append(filename)
                    continue

                lufs = measure_lufs(path)
                if lufs is None:
                    print(f"  {filename:<{name_w}} {'측정실패':>7}")
                    failed.append(filename)
                    continue

                label = zone(lufs)
                print(f"  {filename:<{name_w}} {lufs:>7.1f}  {label}")
                _bucket(buckets, filename, lufs)

        # excluded_sources도 함께 출력
        excluded = entry.get("excluded_sources", {})
        for fname, lufs in excluded.items():
            print(f"  {fname:<{name_w}} {lufs:>7.1f}  ❌  제외됨 (파이프라인 자동 제외)")

    _print_summary(buckets, no_data, not_found, failed)


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
            failed.append(f)
            continue
        label = zone(lufs)
        print(f"{rel:<{name_w}} {lufs:>7.1f}  {label}")
        _bucket(buckets, f, lufs)

    _print_summary(buckets, [], [], failed)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────

def _bucket(buckets, item, lufs):
    if lufs >= -20:
        buckets["safe"].append((item, lufs))
    elif lufs >= -24:
        buckets["warn"].append((item, lufs))
    else:
        buckets["danger"].append((item, lufs))


def _print_summary(buckets, no_data, not_found, failed):
    total = sum(len(v) for v in buckets.values())
    print("\n" + "=" * 75)
    print(f"측정 완료: {total}개  |  파일없음: {len(not_found)}개  |  측정실패: {len(failed)}개\n")
    print(f"  ✅  적당          {len(buckets['safe']):>3}개  (-20 LUFS 이상)")
    print(f"  ⚠️   loudnorm 필요 {len(buckets['warn']):>3}개  (-20 ~ -24 LUFS)")
    print(f"  ❌  제외 권장     {len(buckets['danger']):>3}개  (-24 LUFS 미만)\n")

    if buckets["danger"]:
        print("[ 제외 권장 파일 ]")
        for item, lufs in sorted(buckets["danger"], key=lambda x: x[1]):
            name = item if isinstance(item, str) else item.name
            print(f"  {lufs:>7.1f} LUFS  {name}")

    if not_found:
        print(f"\n[ 파일을 찾지 못함 — output/{{session_id}}/sounds/ 또는 assets/sounds/_used/ 확인 필요 ]")
        for f in not_found:
            print(f"  {f}")


# ── 진입점 ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="소스 오디오 LUFS 측정")
    parser.add_argument("--used-only", action="store_true",
                        help="used_assets.json 기록 기반으로 측정 (기본: assets/sounds/ 전체 스캔)")
    args = parser.parse_args()

    if args.used_only:
        run_used_only()
    else:
        run_full_scan()


if __name__ == "__main__":
    main()
