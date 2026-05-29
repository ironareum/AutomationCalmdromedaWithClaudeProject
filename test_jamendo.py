"""
Jamendo API 수집 단독 테스트 (컨셉 생성 없이)
실행: python test_jamendo.py
"""

import os
import sys
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

client_id = os.getenv("JAMENDO_CLIENT_ID", "")
if not client_id:
    print("❌ JAMENDO_CLIENT_ID 없음 — .env에 추가 필요")
    print("   https://developer.jamendo.com/v3.0 에서 무료 발급")
    sys.exit(1)

print(f"✓ JAMENDO_CLIENT_ID: {client_id[:6]}...")

BASE_URL = "https://api.jamendo.com/v3.0/tracks/"

# 테스트할 태그 목록
TEST_TAGS = ["meditation", "calm", "ambient", "new age", "dreamy"]

SEARCH_TAGS = ["ambient", "newage"]   # 전 카테고리 고정 (genres 기반 2회 호출)

print("\n── genres 기반 검색 테스트 (ambient / newage) ──────────────")
for tag in SEARCH_TAGS:
    params = {
        "client_id":   client_id,
        "format":      "json",
        "limit":       3,
        "fuzzytags":   tag,
        "include":     "musicinfo",
        "audioformat": "mp32",
        "orderby":     "duration_desc",
    }
    resp = requests.get(BASE_URL, params=params, timeout=15)
    data = resp.json()
    headers = data.get("headers", {})
    results = data.get("results", [])

    status = headers.get("status", "?")
    err = headers.get("error_message", "")
    print(f"\n[tag='{tag}'] status={status} | {len(results)} results | err={err or '-'}")

    for t in results:
        mi = t.get("musicinfo", {}) or {}
        tg = mi.get("tags", {}) or {}
        genres = tg.get("genres", [])
        instruments = tg.get("instruments", [])
        vartags = tg.get("vartags", [])
        dur = t.get("duration", 0)
        dl_ok = t.get("audiodownload_allowed", "?")
        dl_url = (t.get("audiodownload") or "")[:50]
        print(f"  • {t.get('name', '?')} ({dur}s) | dl_allowed={dl_ok}")
        print(f"    genres={genres} | instruments={instruments} | vartags={vartags}")
        print(f"    dl_url={dl_url}")

print("\n── 카테고리별 vartags 필터 시뮬레이션 ──────────────────────")
EXCLUDE = ["piano"]
# 카테고리별 vartags (OR 조건)
REQUIRED_VARTAGS_BY_CAT = {
    "mandala":           ["meditative", "meditation", "calm", "mandala"],
    "fractal":           ["meditative", "meditation", "calm"],
    "cosmic_meditation": ["meditative", "meditation", "calm", "dreamy"],
}

for cat, req_vartags in REQUIRED_VARTAGS_BY_CAT.items():
    all_results = []
    seen_ids: set[str] = set()
    for tag in SEARCH_TAGS:
        params = {
            "client_id":   client_id,
            "format":      "json",
            "limit":       10,
            "fuzzytags":   tag,
            "include":     "musicinfo",
            "audioformat": "mp32",
            "orderby":     "duration_desc",
        }
        results = requests.get(BASE_URL, params=params, timeout=15).json().get("results", [])
        for t in results:
            tid = str(t.get("id", ""))
            if tid and tid not in seen_ids:
                seen_ids.add(tid)
                all_results.append(t)

    passed = []
    for t in all_results:
        mi = t.get("musicinfo", {}) or {}
        tg = mi.get("tags", {}) or {}
        vartags_set = {v.lower() for v in (tg.get("vartags")    or [])}
        instruments = {i.lower() for i in (tg.get("instruments")or [])}
        all_tags    = vartags_set | instruments

        ok_vartag = any(v in vartags_set for v in req_vartags)
        ok_excl   = not any(ex in all_tags for ex in EXCLUDE)
        if ok_vartag and ok_excl:
            passed.append(t)

    print(f"[{cat}] {len(all_results)} merged → {len(passed)} passed filter (vartags={req_vartags[:3]}...)")
    for t in passed[:2]:
        print(f"  ✓ {t.get('name')} ({t.get('duration')}s)")
