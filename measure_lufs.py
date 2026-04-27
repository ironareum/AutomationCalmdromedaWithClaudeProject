"""
소스 오디오 LUFS 측정 스크립트

[사용법]
  python measure_lufs.py              # assets/sounds/ 전체 스캔 (파일 직접 측정)
  python measure_lufs.py --used-only  # used_assets.json 기반 Freesound API로 LUFS 조회

[--used-only 동작]
  used_assets.json의 파일명에서 Freesound ID를 파싱 → API 분석 엔드포인트 조회
  파일이 없어도 기존 이력 전체 확인 가능.
  이미 source_lufs가 기록된 세션은 API 호출 없이 바로 출력.

[출력 판정 기준]
  ✅  -20 이상        → loudnorm 스킵 (적당)
  ⚠️  -20 ~ -24 사이  → loudnorm 적용 (안전 범위)
  ❌  -24 미만        → 제외 권장 (왜곡 위험)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

ROOT             = Path(__file__).parent
SOUNDS_DIR       = ROOT / "assets" / "sounds"
USED_ASSETS_FILE = ROOT / "used_assets.json"
AUDIO_EXTS       = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}
FREESOUND_BASE   = "https://freesound.org/apiv2"


# ── 공통 유틸 ──────────────────────────────────────────────────────────────

def zone(lufs: float) -> str:
    if lufs >= -20:
        return "✅  적당"
    elif lufs >= -24:
        return "⚠️  loudnorm 적용"
    else:
        return "❌  제외 권장"


def parse_freesound_id(filename: str) -> str | None:
    """파일명 앞 숫자 블록에서 Freesound ID 추출
    예: 243628_Heavy_Rain.mp3 → '243628'
    """
    part = filename.split("_")[0]
    return part if part.isdigit() else None


# ── Freesound API ──────────────────────────────────────────────────────────

def get_api_key() -> str:
    key = os.getenv("FREESOUND_API_KEY", "")
    if not key:
        print("[오류] FREESOUND_API_KEY 환경변수가 없습니다. .env 파일을 확인하세요.")
        sys.exit(1)
    return key


def fetch_lufs(sound_id: str, api_key: str) -> float | None:
    """Freesound API analysis 엔드포인트로 EBU R128 통합 라우드니스(LUFS) 조회"""
    url = f"{FREESOUND_BASE}/sounds/{sound_id}/analysis/"
    try:
        resp = requests.get(
            url,
            params={"token": api_key, "descriptors": "lowlevel.loudness_ebu128.integrated"},
            timeout=10,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        lufs = (data
                .get("lowlevel", {})
                .get("loudness_ebu128", {})
                .get("integrated"))
        return round(float(lufs), 1) if lufs is not None else None
    except Exception as e:
        print(f"    [API 오류] ID={sound_id}: {e}")
        return None


# ── --used-only 모드 ───────────────────────────────────────────────────────

def run_used_only():
    if not USED_ASSETS_FILE.exists():
        print(f"[오류] used_assets.json 없음: {USED_ASSETS_FILE}")
        sys.exit(1)

    data    = json.loads(USED_ASSETS_FILE.read_text(encoding="utf-8"))
    api_key = get_api_key()

    # 중복 제거: 파일명 → Freesound ID 매핑 사전 구성
    id_map: dict[str, str] = {}   # filename → sound_id
    for entry in data.values():
        for fname in entry.get("sounds", []):
            if fname not in id_map:
                sid = parse_freesound_id(fname)
                if sid:
                    id_map[fname] = sid

    # 고유 ID만 API 조회 (중복 호출 방지)
    unique_ids = list({v for v in id_map.values()})
    print(f"\n총 {len(id_map)}개 음원 파일 / 고유 ID {len(unique_ids)}개 → Freesound API 조회 시작\n")

    lufs_cache: dict[str, float | None] = {}  # sound_id → LUFS
    for i, sid in enumerate(unique_ids):
        lufs_cache[sid] = fetch_lufs(sid, api_key)
        if (i + 1) % 10 == 0:
            time.sleep(0.5)  # API rate limit 방지

    # 세션별 출력
    name_w  = 45
    buckets = {"safe": [], "warn": [], "danger": []}
    no_id, no_data = [], []

    for session_id, entry in sorted(data.items()):
        title    = entry.get("title", session_id)
        sounds   = entry.get("sounds", [])
        quality  = entry.get("quality", "pending")
        recorded = entry.get("source_lufs", {})  # 파이프라인 자동 기록 (PR #25 이후)

        print(f"▶ [{session_id}] {title}  ({quality})")

        for fname in sounds:
            # PR #25 이후 파이프라인이 직접 기록한 데이터 우선
            if fname in recorded and recorded[fname] is not None:
                lufs  = recorded[fname]
                label = zone(lufs)
                print(f"  {fname:<{name_w}} {lufs:>7.1f}  {label}  (기록됨)")
                _add_bucket(buckets, fname, lufs)
                continue

            sid = id_map.get(fname)
            if sid is None:
                print(f"  {fname:<{name_w}} {'ID없음':>7}  (Freesound ID 파싱 불가)")
                no_id.append(fname)
                continue

            lufs = lufs_cache.get(sid)
            if lufs is None:
                print(f"  {fname:<{name_w}} {'분석없음':>7}  (Freesound 분석 데이터 없음)")
                no_data.append(fname)
                continue

            label = zone(lufs)
            print(f"  {fname:<{name_w}} {lufs:>7.1f}  {label}")
            _add_bucket(buckets, fname, lufs)

        # 파이프라인 자동 제외 이력
        for fname, lufs in entry.get("excluded_sources", {}).items():
            print(f"  {fname:<{name_w}} {lufs:>7.1f}  ❌  파이프라인 자동 제외")
            _add_bucket(buckets, fname, lufs)

        print()

    _print_summary(buckets, no_id, no_data)


# ── 전체 스캔 모드 (파일 직접 측정) ──────────────────────────────────────

def measure_lufs_file(file_path: Path) -> float | None:
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
            val = json.loads(match.group()).get("input_i", "")
            if val and val not in ("-inf", "+inf"):
                return round(float(val), 1)
        except (json.JSONDecodeError, ValueError):
            pass
    return None


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
    failed  = []

    for f in files:
        rel  = str(f.relative_to(SOUNDS_DIR))
        lufs = measure_lufs_file(f)
        if lufs is None:
            print(f"{rel:<{name_w}} {'측정실패':>7}")
            failed.append(rel)
            continue
        label = zone(lufs)
        print(f"{rel:<{name_w}} {lufs:>7.1f}  {label}")
        _add_bucket(buckets, rel, lufs)

    _print_summary(buckets, [], failed)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────

def _add_bucket(buckets, item, lufs):
    if lufs >= -20:
        buckets["safe"].append((item, lufs))
    elif lufs >= -24:
        buckets["warn"].append((item, lufs))
    else:
        buckets["danger"].append((item, lufs))


def _print_summary(buckets, no_id, no_data_or_failed):
    total = sum(len(v) for v in buckets.values())
    print("=" * 70)
    print(f"조회 완료: {total}개  |  ID 없음: {len(no_id)}개  |  분석 없음/실패: {len(no_data_or_failed)}개\n")
    print(f"  ✅  적당          {len(buckets['safe']):>3}개  (-20 LUFS 이상)")
    print(f"  ⚠️   loudnorm 필요 {len(buckets['warn']):>3}개  (-20 ~ -24 LUFS)")
    print(f"  ❌  제외 권장     {len(buckets['danger']):>3}개  (-24 LUFS 미만)\n")

    if buckets["danger"]:
        print("[ 제외 권장 파일 ]")
        seen = set()
        for name, lufs in sorted(buckets["danger"], key=lambda x: x[1]):
            key = name if isinstance(name, str) else name.name
            if key not in seen:
                print(f"  {lufs:>7.1f} LUFS  {key}")
                seen.add(key)


# ── 진입점 ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="소스 오디오 LUFS 측정/조회")
    parser.add_argument(
        "--used-only", action="store_true",
        help="used_assets.json 기반으로 Freesound API에서 LUFS 조회 (파일 불필요)"
    )
    args = parser.parse_args()

    if args.used_only:
        run_used_only()
    else:
        run_full_scan()


if __name__ == "__main__":
    main()
