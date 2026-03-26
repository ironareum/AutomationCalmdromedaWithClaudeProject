"""
Pexels API Video Collector
무료 4K 자연 영상 수집
API 키 발급: https://www.pexels.com/api/
"""

import time
import logging
import requests
from pathlib import Path

log = logging.getLogger(__name__)


class PexelsCollector:
    BASE_URL = "https://api.pexels.com/videos"

    def __init__(self, api_key: str, work_dir: Path):
        self.headers = {"Authorization": api_key}
        self.video_dir = work_dir / "videos"
        self.video_dir.mkdir(parents=True, exist_ok=True)

    def search(self, query: str, count: int = 5) -> list[dict]:
        """
        Pexels에서 영상 검색
        """
        params = {
            "query": query,
            "per_page": count,
            "orientation": "landscape",
            "size": "large",  # 최소 4K
        }
        try:
            resp = requests.get(
                f"{self.BASE_URL}/search",
                headers=self.headers,
                params=params,
                timeout=15
            )
            resp.raise_for_status()
            videos = resp.json().get("videos", [])
            log.info(f"Pexels search '{query}': {len(videos)} results")
            return videos
        except requests.RequestException as e:
            log.error(f"Pexels search failed for '{query}': {e}")
            return []

    def get_best_file(self, video: dict, prefer_4k: bool = True) -> dict | None:
        """
        영상 파일 중 최적 해상도 선택
        우선순위: 4K(2160) > FHD(1080) > HD(720)
        """
        files = video.get("video_files", [])
        if not files:
            return None

        # 해상도 기준 정렬
        resolution_priority = {2160: 4, 1440: 3, 1080: 2, 720: 1}
        files_sorted = sorted(
            [f for f in files if f.get("file_type") == "video/mp4"],
            key=lambda f: resolution_priority.get(f.get("height", 0), 0),
            reverse=True
        )
        return files_sorted[0] if files_sorted else None

    def download(self, video: dict, filename: str = None) -> Path | None:
        """
        영상 파일 다운로드
        """
        file_info = self.get_best_file(video)
        if not file_info:
            log.warning(f"No suitable file for video {video.get('id')}")
            return None

        url = file_info.get("link")
        if not url:
            return None

        fname = filename or f"pexels_{video['id']}_{file_info.get('height', 'unknown')}p.mp4"
        dest = self.video_dir / fname

        if dest.exists():
            log.info(f"Video already cached: {dest.name}")
            return dest

        try:
            log.info(f"Downloading video {video['id']} ({file_info.get('height')}p)...")
            resp = requests.get(url, timeout=120, stream=True)
            resp.raise_for_status()

            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)

            size_mb = dest.stat().st_size / (1024 * 1024)
            log.info(f"Downloaded: {dest.name} ({size_mb:.1f}MB)")
            return dest
        except Exception as e:
            log.error(f"Video download failed: {e}")
            if dest.exists():
                dest.unlink()
            return None

    def collect(self, category: str, count: int = 5) -> list[Path]:
        """
        카테고리 기반 영상 수집
        config.py의 category_queries 매핑 사용
        """
        from config import Config
        cfg = Config()
        queries = cfg.category_queries.get(category, [category])

        collected = []
        per_query = max(1, count // len(queries) + 1)

        for query in queries:
            if len(collected) >= count:
                break
            results = self.search(query, count=per_query)
            for video in results:
                if len(collected) >= count:
                    break
                path = self.download(video)
                if path:
                    collected.append(path)
                time.sleep(0.5)

        log.info(f"Total videos collected: {len(collected)}")
        return collected
