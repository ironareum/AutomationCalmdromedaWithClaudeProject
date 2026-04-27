"""
Pixabay Music API Collector
2026.04.27 신규 — zen 파이프라인 전용 음원 수집
2026.04.27 fix: duration 필터 제거 (API 응답에 duration=0으로 내려옴)
               audio URL 필드명 다중 시도, 응답 구조 디버그 로깅 추가

Pixabay Music License: 상업적 사용 무료, 저작자 표시 불필요
API 키 발급: https://pixabay.com/api/docs/
"""

import logging
import time
from pathlib import Path

import requests

from collector.freesound import load_used_assets

log = logging.getLogger(__name__)

BASE_URL = "https://pixabay.com/api/"


def _is_used(track_id: str) -> bool:
    data = load_used_assets()
    return any(
        any(str(track_id) in s for s in entry.get("sounds", []))
        for entry in data.values()
    )


def _extract_audio_url(track: dict) -> str | None:
    """Pixabay API 버전별로 audio URL 필드명이 다를 수 있어 순서대로 시도"""
    for field in ("audio", "audioURL", "audioUrl", "audio_url", "previewURL", "url"):
        val = track.get(field)
        if val and isinstance(val, str) and val.startswith("http"):
            return val
    return None


class PixabayMusicCollector:
    def __init__(self, api_key: str, work_dir: Path):
        self.api_key = api_key
        self.sound_dir = work_dir / "sounds"
        self.sound_dir.mkdir(parents=True, exist_ok=True)
        self._logged_sample = False  # 첫 응답 구조 1회만 로깅

    def search(self, query: str, per_page: int = 20) -> list[dict]:
        """Pixabay Music API 검색 — duration 필터 없이 전체 반환"""
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
            data = resp.json()
            hits = data.get("hits", [])

            # 첫 실행 시 실제 응답 필드 구조 1회 로깅 (디버그용)
            if hits and not self._logged_sample:
                sample = {k: v for k, v in hits[0].items() if k != "userImageURL"}
                log.info(f"Pixabay 응답 샘플 필드: {list(sample.keys())}")
                log.debug(f"Pixabay 샘플 값: {sample}")
                self._logged_sample = True

            log.info(f"Pixabay '{query}': {len(hits)} found")
            return hits
        except Exception as e:
            log.error(f"Pixabay search failed '{query}': {e}")
            return []

    def download(self, track: dict) -> Path | None:
        """트랙 다운로드"""
        audio_url = _extract_audio_url(track)
        if not audio_url:
            log.warning(
                f"Pixabay track {track.get('id')}: audio URL 없음 "
                f"(보유 필드: {[k for k, v in track.items() if v]}) — 스킵"
            )
            return None

        track_id = str(track.get("id", "unknown"))
        title = str(track.get("title") or track.get("tags", "track"))[:25].replace(" ", "_")
        fname = f"pixabay_{track_id}_{title}.mp3"
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
            dur = track.get("duration") or track.get("audioDuration") or "?"
            log.info(f"Pixabay downloaded: {dest.name} ({size_kb}KB, {dur}s)")
            return dest
        except Exception as e:
            log.error(f"Pixabay download failed {track_id}: {e}")
            if dest.exists():
                dest.unlink()
            return None

    def collect(self, queries: list[str], count: int = 1) -> list[Path]:
        """쿼리 목록에서 트랙 count개 수집 (다운로드 수 상위 우선)"""
        collected: list[Path] = []
        seen_ids: set[str] = set()

        for query in queries:
            if len(collected) >= count:
                break
            for track in self.search(query):
                if len(collected) >= count:
                    break
                tid = str(track.get("id", ""))
                if not tid or tid in seen_ids:
                    continue
                if _is_used(tid):
                    continue
                path = self.download(track)
                if path:
                    collected.append(path)
                    seen_ids.add(tid)
                time.sleep(0.3)

        log.info(f"Pixabay 수집 완료: {len(collected)}개")
        return collected
