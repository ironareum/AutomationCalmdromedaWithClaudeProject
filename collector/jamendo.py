"""
Jamendo Music API Collector
2026.04.27 신규 — zen 파이프라인 전용 CC 음악 수집

Jamendo License: CC-BY / CC-BY-SA (상업적 사용 가능, 저작자 표시 필요)
클라이언트 ID 발급: https://developers.jamendo.com → Create App (무료)
환경변수: JAMENDO_CLIENT_ID
"""

import logging
import time
from pathlib import Path

import requests

from collector.freesound import load_used_assets

log = logging.getLogger(__name__)

BASE_URL = "https://api.jamendo.com/v3.0/tracks/"


def _is_used(track_id: str) -> bool:
    data = load_used_assets()
    return any(
        any(str(track_id) in s for s in entry.get("sounds", []))
        for entry in data.values()
    )


class JamendoMusicCollector:
    def __init__(self, client_id: str, work_dir: Path):
        self.client_id = client_id
        self.sound_dir = work_dir / "sounds"
        self.sound_dir.mkdir(parents=True, exist_ok=True)

    def search(self, tags: str, limit: int = 20) -> list[dict]:
        """태그 기반 CC 음악 검색 — duration 내림차순"""
        params = {
            "client_id":    self.client_id,
            "format":       "json",
            "limit":        limit,
            "tags":         tags,
            "audiodlformat": "mp31",
            "order":        "popularity_total",
            "include":      "musicinfo licenses",
        }
        try:
            resp = requests.get(BASE_URL, params=params, timeout=15)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            # 60초 이상만 — Jamendo는 duration 필드 신뢰 가능
            filtered = [r for r in results if int(r.get("duration", 0)) >= 60]
            log.info(f"Jamendo '{tags}': {len(results)} found / {len(filtered)} ≥60s")
            return filtered
        except Exception as e:
            log.error(f"Jamendo search failed '{tags}': {e}")
            return []

    def download(self, track: dict) -> Path | None:
        """트랙 다운로드 — audiodownload 우선, 없으면 audio(스트리밍) 사용"""
        audio_url = track.get("audiodownload") or track.get("audio")
        if not audio_url:
            log.warning(f"Jamendo track {track.get('id')}: audio URL 없음")
            return None

        track_id = str(track.get("id", "unknown"))
        name = str(track.get("name") or "track")[:25].replace(" ", "_")
        artist = str(track.get("artist_name") or "")[:15].replace(" ", "_")
        fname = f"jamendo_{track_id}_{artist}_{name}.mp3"
        fname = "".join(c for c in fname if c.isalnum() or c in "._-")
        dest = self.sound_dir / fname

        if dest.exists():
            log.info(f"Jamendo cached: {dest.name}")
            return dest

        try:
            resp = requests.get(audio_url, timeout=120, stream=True,
                                headers={"User-Agent": "Calmdromeda/1.0"})
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
            size_kb = dest.stat().st_size // 1024
            dur = track.get("duration", "?")
            log.info(f"Jamendo downloaded: {dest.name} ({size_kb}KB, {dur}s)")
            return dest
        except Exception as e:
            log.error(f"Jamendo download failed {track_id}: {e}")
            if dest.exists():
                dest.unlink()
            return None

    def collect(self, tag_queries: list[str], count: int = 1) -> list[Path]:
        """태그 쿼리 목록에서 트랙 count개 수집"""
        collected: list[Path] = []
        seen_ids: set[str] = set()

        for tags in tag_queries:
            if len(collected) >= count:
                break
            for track in self.search(tags):
                if len(collected) >= count:
                    break
                tid = str(track.get("id", ""))
                if not tid or tid in seen_ids:
                    continue
                if _is_used(tid):
                    log.debug(f"Jamendo {tid}: already used — skip")
                    continue
                path = self.download(track)
                if path:
                    collected.append(path)
                    seen_ids.add(tid)
                time.sleep(0.3)

        log.info(f"Jamendo 수집 완료: {len(collected)}개")
        return collected
