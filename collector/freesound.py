"""
Freesound.org API Collector
CC0 라이선스 자연 사운드 자동 수집
API 키 발급: https://freesound.org/apiv2/apply/
"""

import os
import time
import logging
import requests
from pathlib import Path

log = logging.getLogger(__name__)

# CC 라이선스 중 상업적 이용 가능한 것만
ALLOWED_LICENSES = [
    "Creative Commons 0",           # CC0 — 완전 자유
    "Attribution",                  # CC BY — 출처 표기
    #"Attribution NonCommercial",    # CC BY-NC — 비상업 (수익화 시 제외 필요)
]

# 수익화 채널은 CC0, CC BY만 사용 권장
COMMERCIAL_SAFE_LICENSES = [
    "Creative Commons 0",
    "Attribution",
]


class FreesoundCollector:
    BASE_URL = "https://freesound.org/apiv2"

    def __init__(self, api_key: str, work_dir: Path):
        self.api_key = api_key
        self.sound_dir = work_dir / "sounds"
        self.sound_dir.mkdir(parents=True, exist_ok=True)

    def search(self, query: str, page_size: int = 10) -> list[dict]:
        """
        쿼리로 사운드 검색, CC0/CC BY만 필터링
        """
        params = {
            "query": query,
            "page_size": page_size,
            "fields": "id,name,duration,license,previews,download,avg_rating,num_downloads",
            "filter": 'license:"Creative Commons 0" OR license:"Attribution"',
            "sort": "downloads_desc",  # 다운로드 많은 것 우선 (검증된 품질)
            "token": self.api_key,
        }

        try:
            resp = requests.get(f"{self.BASE_URL}/search/text/", params=params, timeout=15)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            log.info(f"Freesound search '{query}': {len(results)} results")
            return results
        except requests.RequestException as e:
            log.error(f"Freesound search failed for '{query}': {e}")
            return []

    def download(self, sound: dict, filename: str = None) -> Path | None:
        """
        사운드 파일 다운로드 (고품질 preview 사용 — OAuth 불필요)
        실제 원본 다운로드는 OAuth2 필요, HQ preview는 API 키만으로 가능
        """
        previews = sound.get("previews", {})

        # HQ MP3 우선, 없으면 LQ
        preview_url = (
            previews.get("preview-hq-mp3") or
            previews.get("preview-lq-mp3")
        )
        if not preview_url:
            log.warning(f"No preview URL for sound {sound['id']}")
            return None

        fname = filename or f"{sound['id']}_{sound['name'][:30].replace(' ', '_')}.mp3"
        fname = "".join(c for c in fname if c.isalnum() or c in "._-")  # sanitize
        dest = self.sound_dir / fname

        if dest.exists():
            log.info(f"Sound already cached: {dest.name}")
            return dest

        try:
            resp = requests.get(preview_url, timeout=30, stream=True)
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            log.info(f"Downloaded: {dest.name} ({dest.stat().st_size // 1024}KB)")
            return dest
        except Exception as e:
            log.error(f"Download failed for {sound['id']}: {e}")
            return None

    def collect(self, queries: list[str], count_per_query: int = 3) -> list[Path]:
        """
        여러 쿼리로 사운드 수집, 중복 제거 후 반환
        """
        collected = []
        seen_ids = set()

        for query in queries:
            results = self.search(query, page_size=count_per_query * 2)

            downloaded = 0
            for sound in results:
                if downloaded >= count_per_query:
                    break
                if sound["id"] in seen_ids:
                    continue
                # 최소 품질 필터: 30초 이상, 평점 있는 것
                if sound.get("duration", 0) < 30:
                    continue

                path = self.download(sound)
                if path:
                    collected.append(path)
                    seen_ids.add(sound["id"])
                    downloaded += 1

                time.sleep(0.3)  # API rate limit 방지

        log.info(f"Total sounds collected: {len(collected)}")
        return collected
