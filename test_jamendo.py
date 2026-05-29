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

print("\n── 태그별 검색 테스트 ──────────────────────────")
for tag in TEST_TAGS:
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

print("\n── required_any 필터 시뮬레이션 ──────────────────")
REQUIRED_ANY = ["ambient", "new age"]
EXCLUDE = ["piano"]
for tag in ["meditation", "calm"]:
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
    passed = []
    for t in results:
        mi = t.get("musicinfo", {}) or {}
        tg = mi.get("tags", {}) or {}
        all_tags = set()
        for group in tg.values():
            if isinstance(group, list):
                all_tags.update(g.lower() for g in group)
        has_required = any(r.lower() in all_tags for r in REQUIRED_ANY)
        has_excluded = any(ex.lower() in all_tags for ex in EXCLUDE)
        if has_required and not has_excluded:
            passed.append(t)

    print(f"tag='{tag}': {len(results)} found → {len(passed)} passed filter")
    for t in passed[:2]:
        print(f"  ✓ {t.get('name')} ({t.get('duration')}s)")
