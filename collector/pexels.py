"""
Pexels API Video Collector
2026.03.26 무료 4K 자연 영상 수집
2026.03.26 API 키 발급: https://www.pexels.com/api/
2026.03.28 사용한 영상은 used_assets.json에 기록 → 다음 실행 시 자동 스킵
2026.03.29 used_assetss.json 포맷형식 변경
2026.03.29 [Phase2] AI 기획 자동화 (Claude API) + sound,video 쿼리에도 적용
2026.04.07 feat: 로컬 영상 폴더 지원 (assets/video/), 영상 기본 수 3개로 변경
2026.04.07 feat: Pexels 영상 검색 no people 키워드 추가
2026.04.07 fix: Pexels size large → medium (1080p 이상 허용, 선택지 확대
2026.04.07 feat: Pexels 긴 영상 우선 정렬, bath_house 실내 전용으로 변경
"""

import time
import logging
import requests
from pathlib import Path
from collector.freesound import load_used_assets, save_used_assets, is_video_used

LOCAL_VIDEO_DIR = Path(__file__).parent.parent / "assets" / "video"

log = logging.getLogger(__name__)


class PexelsCollector:
    BASE_URL = "https://api.pexels.com/videos"

    def __init__(self, api_key: str, work_dir: Path, session_id: str = ""):
        self.headers    = {"Authorization": api_key}
        self.session_id = session_id  # used_assets 기록에 사용
        self.video_dir  = work_dir / "videos"
        self.video_dir.mkdir(parents=True, exist_ok=True)
        self.used = load_used_assets()
        log.info(f"Used sessions so far: {len(self.used)}")

    def search(self, query: str, count: int = 10) -> list[dict]:
        """
        Pexels에서 영상 검색 (사람 없는 영상 우선)
        """
        # 사람 없는 영상 유도 키워드 추가
        no_people_query = f"{query} no people"
        params = {
            "query": no_people_query,
            "per_page": count,
            "orientation": "landscape",
            "size": "medium",  # 1080p 이상 (선택지 확대)
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

            # 이미 사용한 영상 필터링
            fresh = [v for v in videos if not is_video_used(str(v["id"]))]

            # 사람 관련 키워드 포함 영상 제외
            PEOPLE_KEYWORDS = ["people", "person", "man", "woman", "girl", "boy",
                                "human", "crowd", "face", "portrait", "model",
                                "사람", "남자", "여자", "인물"]
            def has_people(v):
                text = " ".join([
                    v.get("url", ""),
                    str(v.get("user", {}).get("name", "")),
                    " ".join(str(t) for t in v.get("tags", [])),
                ]).lower()
                return any(kw in text for kw in PEOPLE_KEYWORDS)

            no_people = [v for v in fresh if not has_people(v)]
            people_count = len(fresh) - len(no_people)
            pool = no_people if no_people else fresh  # 없으면 원본 사용

            skipped = len(videos) - len(fresh)
            # 긴 영상 우선 정렬
            pool = sorted(pool, key=lambda v: v.get("duration", 0), reverse=True)
            log.info(f"Pexels '{query}': {len(videos)} found / {skipped} skipped (used) / {people_count} people filtered / {len(pool)} fresh (duration sorted)")
            return pool
        except requests.RequestException as e:
            log.error(f"Pexels search failed '{query}': {e}")
            return []

    def get_best_file(self, video: dict, prefer_4k: bool = True) -> dict | None:
        """
        영상 파일 중 최적 선택
        우선순위: 긴 영상 + 고해상도
        """
        files = video.get("video_files", [])
        if not files:
            return None

        resolution_priority = {2160: 4, 1440: 3, 1080: 2, 720: 1}
        mp4_files = [f for f in files if f.get("file_type") == "video/mp4"]
        # 해상도 + 영상 길이(duration) 복합 정렬 (긴 영상 우선)
        duration = video.get("duration", 0)
        files_sorted = sorted(
            mp4_files,
            key=lambda f: (resolution_priority.get(f.get("height", 0), 0), duration),
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
            log.info(f"Downloading video  {video['id']}_{file_info.get('height')}...")
            resp = requests.get(url, timeout=120, stream=True)
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)

            size_mb = dest.stat().st_size / (1024 * 1024)
            log.info(f"Downloaded: {dest.name} ({size_mb:.1f}MB)")

            # 사용 완료 → 기록
            # 사용 기록은 pipeline._cleanup_assets() 완료 후 register_used_session()으로 일괄 등록
            return dest
        except Exception as e:
            log.error(f"Video download failed {video['id']}: {e}")
            if dest.exists():
                dest.unlink()
            return None

    def collect_local(self, category: str, count: int = 3) -> list[Path]:
        """assets/video/{category}/ 폴더에서 로컬 영상 수집"""
        local_dir = LOCAL_VIDEO_DIR / category
        if not local_dir.exists():
            return []
        files = sorted(local_dir.glob("*.mp4"))[:count]
        if files:
            # work_dir/videos/ 로 복사
            result = []
            for f in files:
                dest = self.video_dir / f.name
                if not dest.exists():
                    import shutil
                    shutil.copy2(f, dest)
                result.append(dest)
            log.info(f"로컬 영상 {len(result)}개 사용: {local_dir}")
        return result

    def collect(self, category: str, count: int = 3,
                queries: list[str] | None = None) -> list[Path]:
        """
        카테고리 기반 영상 수집
        1단계: assets/video/{category}/ 로컬 폴더 확인
        2단계: Pexels API 수집
        queries가 주어지면 그걸 사용, 없으면 config.py의 category_queries 매핑 사용
        """
        # 1단계: 로컬 영상 우선
        local_files = self.collect_local(category, count)
        if len(local_files) >= count:
            log.info(f"로컬 영상만으로 충분 ({len(local_files)}개) — Pexels API 스킵")
            return local_files[:count]
        if local_files:
            log.info(f"로컬 영상 {len(local_files)}개 — Pexels에서 {count - len(local_files)}개 추가 수집")

        # 2단계: Pexels API
        if queries:
            log.info(f"AI 생성 video queries: {queries}")
        else:
            from config import Config
            cfg = Config()
            queries = cfg.category_queries.get(category, [category])

        collected = list(local_files)
        need = count - len(collected)
        per_query = max(2, need // max(len(queries), 1) + 1)

        for query in queries:
            if len(collected) >= count:
                break
            results = self.search(query, count=per_query * 3)
            for video in results:
                if len(collected) >= count:
                    break
                path = self.download(video)
                if path:
                    collected.append(path)
                time.sleep(0.5)

        log.info(f"Total videos collected: {len(collected)}")
        return collected[:count]