"""
Jamendo Music API Collector
2026.05.29 신규 — mandala 파이프라인 전용 음원 수집

Jamendo License: CC (상업적 사용 무료)
API 키 발급: https://developer.jamendo.com/v3.0
  - 무료 등록 후 client_id 발급
  - Rate limit: 초당 3건, 일 5만건

엔드포인트: https://api.jamendo.com/v3.0/tracks/
"""

import logging
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://api.jamendo.com/v3.0/tracks/"


class JamendoCollector:
    def __init__(self, client_id: str, work_dir: Path):
        self.client_id = client_id
        self.sound_dir = work_dir / "sounds"
        self.sound_dir.mkdir(parents=True, exist_ok=True)

    def search(
        self,
        tags: list[str],
        required_genres: list[str] | None = None,
        required_vartags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """
        태그별 개별 검색 후 머지.
        tags: 각 태그를 개별 API 호출 후 결과 합산 (OR)
        required_genres:  genres 필드 OR — 하나라도 있으면 통과 (e.g. ["ambient", "newage"])
        required_vartags: vartags 필드 OR — 하나라도 있으면 통과 (e.g. ["meditative", "meditation", "calm"])
        두 required 조건은 AND (둘 다 만족해야 통과)
        exclude_tags: 전체 태그에 하나라도 있으면 제외 (e.g. ["piano"])
        """
        seen_ids: set[str] = set()
        merged: list[dict] = []

        for tag in tags:
            params = {
                "client_id":   self.client_id,
                "format":      "json",
                "limit":       limit,
                "fuzzytags":   tag,
                "include":     "musicinfo",
                "audioformat": "mp32",
                "orderby":     "duration_desc",
            }
            try:
                resp = requests.get(BASE_URL, params=params, timeout=15)
                resp.raise_for_status()
                results = resp.json().get("results", [])
                log.info(f"Jamendo '{tag}': {len(results)} found")
                for track in results:
                    tid = str(track.get("id", ""))
                    if tid and tid not in seen_ids:
                        seen_ids.add(tid)
                        merged.append(track)
            except Exception as e:
                log.error(f"Jamendo search failed '{tag}': {e}")
            time.sleep(0.3)

        log.info(f"Jamendo merged total: {len(merged)} unique tracks")

        filtered = []
        for track in merged:
            mi = track.get("musicinfo", {}) or {}
            tg = mi.get("tags", {}) or {}
            genres     = {g.lower() for g in (tg.get("genres")      or [])}
            vartags    = {v.lower() for v in (tg.get("vartags")      or [])}
            instruments= {i.lower() for i in (tg.get("instruments")  or [])}
            all_tags   = genres | vartags | instruments

            # genres 조건: ambient 또는 newage 중 하나 포함
            if required_genres and not any(g in genres for g in required_genres):
                log.debug(f"skip (genre 없음): {track.get('name')} genres={genres}")
                continue

            # vartags 조건: meditative / meditation / calm 중 하나 포함
            if required_vartags and not any(v in vartags for v in required_vartags):
                log.debug(f"skip (vartag 없음): {track.get('name')} vartags={vartags}")
                continue

            # 제외 태그: 전체 태그에 하나라도 있으면 제외
            if exclude_tags and any(ex in all_tags for ex in exclude_tags):
                log.debug(f"skip (excluded): {track.get('name')}")
                continue

            filtered.append(track)

        filtered.sort(key=lambda t: int(t.get("duration", 0)), reverse=True)

        log.info(
            f"Jamendo after filter "
            f"(genres={required_genres}, vartags={required_vartags}, exclude={exclude_tags}): "
            f"{len(filtered)} tracks"
        )
        return filtered

    def download(self, track: dict) -> Path | None:
        """audiodownload URL로 트랙 다운로드"""
        if not track.get("audiodownload_allowed", True):
            log.warning(f"Jamendo {track.get('id')}: download not allowed — skip")
            return None

        audio_url = track.get("audiodownload") or track.get("audio")
        if not audio_url:
            log.warning(f"Jamendo {track.get('id')}: audio URL 없음 — skip")
            return None

        track_id = str(track.get("id", "unknown"))
        name = str(track.get("name") or "track")[:30].replace(" ", "_")
        name = "".join(c for c in name if c.isalnum() or c in "_-")
        fname = f"jamendo_{track_id}_{name}.mp3"
        dest = self.sound_dir / fname

        if dest.exists():
            log.info(f"Jamendo cached: {dest.name}")
            return dest

        try:
            resp = requests.get(audio_url, timeout=120, stream=True)
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

    def collect_longest(
        self,
        tags: list[str],
        required_genres: list[str] | None = None,
        required_vartags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
    ) -> Path | None:
        """태그로 검색 후 가장 긴 트랙 1개 다운로드."""
        tracks = self.search(
            tags,
            required_genres=required_genres,
            required_vartags=required_vartags,
            exclude_tags=exclude_tags,
            limit=20,
        )
        if not tracks:
            log.error("Jamendo: 검색 결과 없음")
            return None

        for track in tracks:
            path = self.download(track)
            if path:
                dur = track.get("duration", 0)
                log.info(
                    f"Jamendo 최장 트랙: {track.get('name')} "
                    f"({dur}s / {int(dur)//60}min {int(dur)%60}s)"
                )
                return path
            time.sleep(0.3)

        log.error("Jamendo: 다운로드 가능한 트랙 없음")
        return None


def _extract_all_tags(track: dict) -> set[str]:
    """musicinfo.tags 내 모든 태그를 소문자 set으로 반환"""
    tags: set[str] = set()
    music_info = track.get("musicinfo", {})
    tag_groups = music_info.get("tags", {})
    for group in tag_groups.values():
        if isinstance(group, list):
            tags.update(t.lower() for t in group)
    # name/artist 내 piano 단어도 체크
    for field in ("name", "artist_name"):
        val = str(track.get(field, "")).lower()
        tags.update(val.split())
    return tags
