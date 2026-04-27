"""
Pixabay Music API Collector
2026.04.27 신규 — zen 파이프라인 전용 음원 수집

Pixabay Music License: 상업적 사용 무료, 저작자 표시 불필요
API 키 발급: https://pixabay.com/api/docs/
"""

import json
import logging
import time
from pathlib import Path

import requests

from collector.freesound import load_used_assets

log = logging.getLogger(__name__)

BASE_URL = "https://pixabay.com/api/"

# 음원 최소 길이 (초) — 8h 루프용으로는 60초 이상이면 충분
MIN_DURATION_SEC = 60


def _is_used(track_id: str) -> bool:
    data = load_used_assets()
    return any(
        any(str(track_id) in s for s in entry.get("sounds", []))
        for entry in data.values()
        if entry.get("session_type") == "zen"
    )


class PixabayMusicCollector:
    def __init__(self, api_key: str, work_dir: Path):
        self.api_key = api_key
        self.sound_dir = work_dir / "sounds"
        self.sound_dir.mkdir(parents=True, exist_ok=True)

    def search(self, query: str, per_page: int = 20) -> list[dict]:
        """Pixabay Music API 검색"""
        params = {
            "key":        self.api_key,
            "q":          query,
            "media_type": "music",
            "per_page":   per_page,
            "order":      "popular",
        }
        try:
            resp = requests.get(BASE_URL, params=params, timeout=15)
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
            # 최소 길이 필터
            filtered = [h for h in hits if h.get("duration", 0) >= MIN_DURATION_SEC]
            log.info(f"Pixabay '{query}': {len(hits)} found / {len(filtered)} ≥{MIN_DURATION_SEC}s")
            return filtered
        except Exception as e:
            log.error(f"Pixabay search failed '{query}': {e}")
            return []

    def download(self, track: dict) -> Path | None:
        """트랙 다운로드 — Pixabay audio URL 직접 다운"""
        audio_url = track.get("audio") or track.get("audioURL") or track.get("url")
        if not audio_url:
            log.warning(f"Pixabay track {track.get('id')}: audio URL 없음 — 스킵")
            return None

        track_id = str(track.get("id", "unknown"))
        fname = f"pixabay_{track_id}_{track.get('title', 'track')[:25].replace(' ', '_')}.mp3"
        fname = "".join(c for c in fname if c.isalnum() or c in "._-")
        dest = self.sound_dir / fname

        if dest.exists():
            log.info(f"Pixabay cached: {dest.name}")
            return dest

        try:
            resp = requests.get(audio_url, timeout=60, stream=True)
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
            size_kb = dest.stat().st_size // 1024
            log.info(f"Pixabay downloaded: {dest.name} ({size_kb}KB, {track.get('duration', 0)}s)")
            return dest
        except Exception as e:
            log.error(f"Pixabay download failed {track_id}: {e}")
            if dest.exists():
                dest.unlink()
            return None

    def collect(self, queries: list[str], count: int = 1) -> list[Path]:
        """
        쿼리 목록에서 최적 트랙 count개 수집
        - 이미 사용한 트랙 자동 스킵
        - 다운로드 수 기준 상위 트랙 우선
        """
        collected: list[Path] = []
        seen_ids: set[str] = set()

        for query in queries:
            if len(collected) >= count:
                break
            results = self.search(query)
            for track in results:
                if len(collected) >= count:
                    break
                tid = str(track.get("id", ""))
                if not tid or tid in seen_ids:
                    continue
                if _is_used(tid):
                    log.debug(f"Pixabay {tid}: already used — skip")
                    continue
                path = self.download(track)
                if path:
                    collected.append(path)
                    seen_ids.add(tid)
                time.sleep(0.3)

        log.info(f"Pixabay 수집 완료: {len(collected)}개")
        return collected
