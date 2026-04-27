"""
소스 오디오 LUFS 측정 스크립트

[사용법]
  python measure_lufs.py              # 전체 측정
  python measure_lufs.py --debug N   # N개 ID만 측정 (기본 3개)

[동작]
  used_assets.json의 파일명에서 Freesound ID 파싱
  → GET /apiv2/sounds/{id}/?fields=previews 로 HQ 미리보기 URL 획득
  → 임시 다운로드 후 ffmpeg 로컬 측정 → 임시파일 삭제
  → lufs_cache.json 캐시 저장 (재실행 시 API·다운로드 생략)
  → lufs_report.txt 결과 파일 저장

[출력 판정 기준]  ※ 파이프라인 소스 제외 임계값 기준
  ✅  -28 이상        → 소스 통과 (사용 가능)
  ⚠️  -28 ~ -35 사이  → loudnorm 주의 (17 dB 이내 증폭)
  ❌  -35 미만        → 제외 권장 (왜곡 위험)
"""

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

ROOT             = Path(__file__).parent
USED_ASSETS_FILE = ROOT / "used_assets.json"
CACHE_FILE       = ROOT / "lufs_cache.json"
REPORT_FILE      = ROOT / "lufs_report.txt"
FREESOUND_BASE   = "https://freesound.org/apiv2"


# ── 공통 유틸 ──────────────────────────────────────────────────────────────

def zone(lufs: float) -> str:
    if lufs >= -28:
        return "✅  통과"
    elif lufs >= -35:
        return "⚠️  loudnorm 주의"
    else:
        return "❌  제외 권장"


def parse_freesound_id(filename: str) -> str | None:
    """파일명 앞 숫자 블록에서 Freesound ID 추출
    예: 243628_Heavy_Rain.mp3 → '243628'
    """
    part = filename.split("_")[0]
    return part if part.isdigit() else None


def load_cache() -> dict[str, float | None]:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_cache(cache: dict[str, float | None]):
    CACHE_FILE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── Freesound API ──────────────────────────────────────────────────────────

def get_api_key() -> str:
    key = os.getenv("FREESOUND_API_KEY", "")
    if not key:
        print("[오류] FREESOUND_API_KEY 환경변수가 없습니다. .env 파일을 확인하세요.")
        sys.exit(1)
    return key


def fetch_preview_url(sound_id: str, api_key: str) -> str | None:
    """Freesound API에서 HQ MP3 미리보기 URL 획득"""
    url = f"{FREESOUND_BASE}/sounds/{sound_id}/"
    try:
        resp = requests.get(
            url,
            params={"token": api_key, "fields": "id,name,previews"},
            timeout=10,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return data.get("previews", {}).get("preview-hq-mp3")
    except Exception as e:
        print(f"    [API 오류] ID={sound_id}: {e}")
        return None


# ── ffmpeg 로컬 측정 ────────────────────────────────────────────────────────

def measure_lufs_from_file(audio_path: Path) -> float | None:
    """ffmpeg loudnorm 분석 모드로 LUFS 측정"""
    import subprocess
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        "-i", str(audio_path),
        "-af", "loudnorm=I=-18:TP=-1.5:LRA=11:print_format=json",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        match = re.search(r'\{[^{}]+\}', result.stderr, re.DOTALL)
        if match:
            data = json.loads(match.group())
            val = data.get("input_i", "")
            if val and val not in ("-inf", "+inf"):
                return round(float(val), 1)
    except Exception as e:
        print(f"    [측정 오류] {audio_path.name}: {e}")
    return None


def download_and_measure(sound_id: str, preview_url: str) -> float | None:
    """미리보기 MP3 다운로드 → LUFS 측정 → 임시파일 삭제"""
    try:
        resp = requests.get(preview_url, timeout=30, stream=True)
        resp.raise_for_status()
    except Exception as e:
        print(f"    [다운로드 오류] ID={sound_id}: {e}")
        return None

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        for chunk in resp.iter_content(chunk_size=8192):
            tmp.write(chunk)

    try:
        return measure_lufs_from_file(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


# ── 보고서 저장 ────────────────────────────────────────────────────────────

def save_report(lines: list[str]):
    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n보고서 저장 완료 → {REPORT_FILE}")


# ── 메인 ──────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="소스 오디오 LUFS 측정")
    parser.add_argument("--debug", metavar="N", type=int, nargs="?", const=3,
                        help="N개 ID만 측정 (기본 3개)")
    args = parser.parse_args()

    if not USED_ASSETS_FILE.exists():
        print(f"[오류] used_assets.json 없음: {USED_ASSETS_FILE}")
        sys.exit(1)

    data    = json.loads(USED_ASSETS_FILE.read_text(encoding="utf-8"))
    api_key = get_api_key()
    cache   = load_cache()

    # 파일명 → Freesound ID 매핑 (중복 제거)
    id_map: dict[str, str] = {}
    for entry in data.values():
        for fname in entry.get("sounds", []):
            if fname not in id_map:
                sid = parse_freesound_id(fname)
                if sid:
                    id_map[fname] = sid

    unique_ids = list({v for v in id_map.values()})
    cached_ids = [sid for sid in unique_ids if sid in cache]
    new_ids    = [sid for sid in unique_ids if sid not in cache]

    if args.debug is not None:
        new_ids = new_ids[:args.debug]
        print(f"\n[DEBUG 모드] 신규 {args.debug}개 ID만 측정\n")
    else:
        print(f"\n총 고유 ID {len(unique_ids)}개 "
              f"(캐시 {len(cached_ids)}개 / 신규 측정 {len(new_ids)}개)\n")

    # 신규 ID: 미리보기 다운로드 + ffmpeg 측정
    for i, sid in enumerate(new_ids):
        print(f"  [{i+1}/{len(new_ids)}] ID={sid} 측정 중...", end=" ", flush=True)
        preview_url = fetch_preview_url(sid, api_key)
        if not preview_url:
            print("미리보기 URL 없음")
            cache[sid] = None
            continue
        lufs = download_and_measure(sid, preview_url)
        cache[sid] = lufs
        label = f"{lufs:.1f} LUFS  {zone(lufs)}" if lufs is not None else "측정 실패"
        print(label)
        if (i + 1) % 5 == 0:
            save_cache(cache)
            time.sleep(0.5)

    save_cache(cache)

    # ── 세션별 출력 및 보고서 작성 ──────────────────────────────────────────
    name_w  = 45
    buckets = {"safe": [], "warn": [], "danger": []}
    no_id, no_data = [], []
    report_lines: list[str] = []

    def rprint(line: str = ""):
        print(line)
        report_lines.append(line)

    rprint(f"{'=' * 70}")
    rprint(f"LUFS 측정 보고서  ({time.strftime('%Y-%m-%d %H:%M:%S')})")
    rprint(f"{'=' * 70}")
    rprint()

    for session_id, entry in sorted(data.items()):
        title    = entry.get("title", session_id)
        sounds   = entry.get("sounds", [])
        quality  = entry.get("quality", "pending")
        recorded = entry.get("source_lufs", {})

        rprint(f"▶ [{session_id}] {title}  ({quality})")

        for fname in sounds:
            # 파이프라인 직접 기록 데이터 우선
            if fname in recorded and recorded[fname] is not None:
                lufs = recorded[fname]
                line = f"  {fname:<{name_w}} {lufs:>7.1f}  {zone(lufs)}  (기록됨)"
                rprint(line)
                _add_bucket(buckets, fname, lufs)
                continue

            sid = id_map.get(fname)
            if sid is None:
                line = f"  {fname:<{name_w}} {'ID없음':>7}  (Freesound ID 파싱 불가)"
                rprint(line)
                no_id.append(fname)
                continue

            lufs = cache.get(sid)
            if lufs is None:
                line = f"  {fname:<{name_w}} {'측정불가':>7}  (미리보기 없음 또는 측정 실패)"
                rprint(line)
                no_data.append(fname)
                continue

            line = f"  {fname:<{name_w}} {lufs:>7.1f}  {zone(lufs)}"
            rprint(line)
            _add_bucket(buckets, fname, lufs)

        for fname, lufs in entry.get("excluded_sources", {}).items():
            line = f"  {fname:<{name_w}} {lufs:>7.1f}  ❌  파이프라인 자동 제외"
            rprint(line)
            _add_bucket(buckets, fname, lufs)

        rprint()

    # 요약
    total = sum(len(v) for v in buckets.values())
    rprint("=" * 70)
    rprint(f"조회 완료: {total}개  |  ID 없음: {len(no_id)}개  |  측정 불가: {len(no_data)}개")
    rprint()
    rprint(f"  ✅  통과          {len(buckets['safe']):>3}개  (-28 LUFS 이상)")
    rprint(f"  ⚠️   loudnorm 주의 {len(buckets['warn']):>3}개  (-28 ~ -35 LUFS)")
    rprint(f"  ❌  제외 권장     {len(buckets['danger']):>3}개  (-35 LUFS 미만)")
    rprint()

    if buckets["danger"]:
        rprint("[ 제외 권장 파일 ]")
        seen = set()
        for name, lufs in sorted(buckets["danger"], key=lambda x: x[1]):
            if name not in seen:
                rprint(f"  {lufs:>7.1f} LUFS  {name}")
                seen.add(name)
        rprint()

    save_report(report_lines)


def _add_bucket(buckets, item, lufs):
    if lufs >= -28:
        buckets["safe"].append((item, lufs))
    elif lufs >= -35:
        buckets["warn"].append((item, lufs))
    else:
        buckets["danger"].append((item, lufs))


if __name__ == "__main__":
    main()
