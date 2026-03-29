"""
Freesound.org API Collector
2026.03.26 CC0/CC BY 라이선스 자연 사운드 자동 수집
2026.03.26 API 키 발급: https://freesound.org/apiv2/apply/
2026.03.28 사용한 소스는 used_assets.json에 기록 → 다음 실행 시 자동 스킵
2026.03.28 로컬 음원 폴백: assets/sounds/{category}/ 폴더 파일 우선 사용
2026.03.29 used_assets.json에 등록일시(session_id) 포함
2026.03.29 로컬 사용 음원 → assets/sounds/_used/ 로 자동 이동 (재사용 방지)

[사운드 수집 우선순위]
1. assets/sounds/{category}/ 폴더에 파일 있으면 → 로컬 파일 우선 사용
2. 로컬 파일 없거나 부족하면 → Freesound API로 자동 수집
3. Freesound도 다운된 경우 → 로컬 파일만으로 진행 (없으면 실패)
"""

import shutil
import time
import json
import logging
import requests
from pathlib import Path

log = logging.getLogger(__name__)

# 사용한 asset 관리
USED_ASSETS_FILE = Path(__file__).parent.parent / "used_assets.json"

# 로컬 음원 폴더 루트
LOCAL_SOUNDS_DIR = Path(__file__).parent.parent / "assets" / "sounds"

# 지원 음원 확장자
SOUND_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}

# category → 로컬 폴더명 매핑
CATEGORY_TO_LOCAL_DIR = {
    "rain":        ["rain"],
    "rain_thunder": ["rain", "thunder"],
    "ocean":       ["ocean"],
    "forest":      ["forest", "birds"],
    "birds":       ["birds", "forest"],
    "white_noise": ["white_noise"],
    "cafe":        ["cafe", "rain"],
    "camping":     ["camping", "forest"],
}


def load_used_assets() -> dict:
    if USED_ASSETS_FILE.exists():
        data = json.loads(USED_ASSETS_FILE.read_text(encoding="utf-8"))
        # 하위 호환: 기존 str 형태 → dict 형태로 마이그레이션
        for key in ("freesound", "pexels"):
            data[key] = [
                {"id": e, "session": "unknown"} if isinstance(e, str) else e
                for e in data.get(key, [])
            ]
        return data
    return {"freesound": [], "pexels": []}


def save_used_assets(data: dict):
    USED_ASSETS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


class LocalSoundCollector:
    """
    assets/sounds/ 폴더에서 음원 파일을 수집
    Freesound API 없이도 동작하는 오프라인 폴백
    """

    def __init__(self, work_dir: Path, session_id: str = ""):
        self.work_dir   = work_dir
        self.session_id = session_id

    def collect_by_queries(self, queries: list[str], count_per_query: int = 3) -> list[Path]:
        """
        쿼리 키워드 → 카테고리 폴더 매핑으로 로컬 음원 수집
        예: "heavy rain" → assets/sounds/rain/ 폴더
        """
        # 쿼리 키워드에서 카테고리 추론
        categories = self._queries_to_categories(queries)
        return self.collect_by_categories(categories, count_per_query)

    def collect_by_categories(self, categories: list[str], count: int = 3) -> list[Path]:
        """
        카테고리 폴더에서 직접 음원 수집
        """
        collected = []
        seen = set()

        for category in categories:
            folder = LOCAL_SOUNDS_DIR / category
            if not folder.exists():
                log.debug(f"Local sound folder not found: {folder}")
                continue

            files = [
                f for f in folder.iterdir()
                if f.suffix.lower() in SOUND_EXTENSIONS
                and f.name not in seen
                and f.name != "README.txt"
            ]

            if not files:
                log.debug(f"No sound files in: {folder}")
                continue

            for f in files[:count]:
                if f.name not in seen:
                    collected.append(f)
                    seen.add(f.name)
                    log.info(f"Local sound: {f.parent.name}/{f.name}")
                    # 사용한 음원 → _used/ 폴더로 이동 (재사용 방지)
                    self._move_to_used(f)

        if collected:
            log.info(f"Local sounds found: {len(collected)} files")
        else:
            log.info(f"No local sounds found in assets/sounds/")

        return collected

    def _move_to_used(self, sound_file: Path):
        """
        로컬 음원을 assets/sounds/_used/{session_id}/ 로 이동
        - 재사용 방지
        - session_id 폴더로 구분 → 어떤 영상에서 썼는지 추적 가능
        """
        session_label = self.session_id or "unknown"
        dest_dir = LOCAL_SOUNDS_DIR / "_used" / session_label
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / sound_file.name
        try:
            shutil.move(str(sound_file), str(dest))
            log.info(f"Moved to _used: {sound_file.name} → _used/{session_label}/")
        except Exception as e:
            log.warning(f"음원 이동 실패 ({sound_file.name}): {e}")

    def _queries_to_categories(self, queries: list[str]) -> list[str]:
        """쿼리 문자열에서 카테고리 폴더명 추론"""
        keyword_map = {
            "rain":     "rain",
            "thunder":  "thunder",
            "storm":    "thunder",
            "ocean":    "ocean",
            "wave":     "ocean",
            "sea":      "ocean",
            "forest":   "forest",
            "bird":     "birds",
            "nature":   "forest",
            "cafe":     "cafe",
            "coffee":   "cafe",
            "camp":     "camping",
            "fire":     "camping",
            "noise":    "white_noise",
            "white":    "white_noise",
        }
        categories = []
        for query in queries:
            for keyword, category in keyword_map.items():
                if keyword in query.lower() and category not in categories:
                    categories.append(category)

        # 매핑 안 되면 첫 쿼리 단어로 폴더 시도
        if not categories and queries:
            fallback = queries[0].split()[0].lower()
            categories.append(fallback)

        return categories


class FreesoundCollector:
    BASE_URL = "https://freesound.org/apiv2"

    def __init__(self, api_key: str, work_dir: Path, session_id: str = ""):
        self.api_key    = api_key
        self.session_id = session_id  # used_assets 기록에 사용
        self.sound_dir  = work_dir / "sounds"
        self.sound_dir.mkdir(parents=True, exist_ok=True)
        self.used  = load_used_assets()
        self.local = LocalSoundCollector(work_dir, session_id=session_id)
        log.info(f"Used sounds so far: {len(self.used['freesound'])} IDs blocked")

    def _used_ids(self, key: str) -> set:
        """used_assets의 id 집합 반환 (dict 구조 대응)"""
        return {e["id"] if isinstance(e, dict) else e for e in self.used.get(key, [])}

    def _is_api_available(self) -> bool:
        """Freesound API 서버 상태 빠르게 체크"""
        try:
            resp = requests.get(
                f"{self.BASE_URL}/search/text/",
                params={"query": "test", "page_size": 1, "token": self.api_key},
                timeout=5
            )
            # HTML 응답이면 점검 중
            content_type = resp.headers.get("Content-Type", "")
            if "html" in content_type or resp.text.strip().startswith("<!"):
                log.warning("Freesound API is down (maintenance page detected)")
                return False
            return True
        except Exception:
            log.warning("Freesound API unreachable")
            return False

    def search(self, query: str, page_size: int = 15) -> list[dict]:
        params = {
            "query": query,
            "page_size": page_size,
            "fields": "id,name,duration,license,previews,avg_rating,num_downloads",
            "filter": 'license:"Creative Commons 0" OR license:"Attribution"',
            "sort": "downloads_desc",  # 다운로드 많은 것 우선 (검증된 품질)
            "token": self.api_key,
        }
        try:
            resp = requests.get(f"{self.BASE_URL}/search/text/", params=params, timeout=15)
            resp.raise_for_status()

            """
            # 오류발생시 원인 확인용 temp log
            print(f"[DEBUG] Status: {resp.status_code}") 
            print(f"[DEBUG] Response: {resp.text[:300]}")
            """
            results = resp.json().get("results", [])

            # 이미 사용한 소스 필터링
            used_ids = self._used_ids("freesound")
            fresh = [r for r in results if str(r["id"]) not in used_ids]
            skipped = len(results) - len(fresh)
            if skipped:
                log.info(f"Freesound '{query}': {len(results)} found / {skipped} skipped (used) / {len(fresh)} fresh")
            else:
                log.info(f"Freesound '{query}': {len(fresh)} fresh results")
            return fresh
        except Exception as e:
            log.error(f"Freesound search failed '{query}': {e}")
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

            # 사용 완료 → 기록
            self.used["freesound"].append({
                "id": str(sound["id"]),
                "session": self.session_id
            })
            save_used_assets(self.used)
            return dest
        except Exception as e:
            log.error(f"Sound download failed {sound['id']}: {e}")
            return None

    def collect(self, queries: list[str], count_per_query: int = 3) -> list[Path]:
        """
        1단계: 로컬 assets/sounds/ 폴더 확인
        2단계: 로컬 부족하면 Freesound API 시도
        3단계: API도 안 되면 로컬 파일만으로 진행
        """
        needed = len(queries) * count_per_query

        # ── 1단계: 로컬 음원 수집 ──────────────────────────────
        local_files = self.local.collect_by_queries(queries, count_per_query)

        if len(local_files) >= needed:
            log.info(f"Using local sounds only ({len(local_files)} files) — Freesound API skipped")
            return local_files

        if local_files:
            log.info(f"Local sounds: {len(local_files)} files. Need {needed - len(local_files)} more from Freesound...")
        else:
            log.info("No local sounds. Trying Freesound API...")

        # ── 2단계: Freesound API 상태 확인 ────────────────────
        if not self._is_api_available():
            if local_files:
                log.warning(f"Freesound down — proceeding with {len(local_files)} local files only")
                return local_files
            else:
                log.error("Freesound down AND no local sounds found.")
                log.error(f"Please add sound files to: assets/sounds/{{category}}/")
                return []

        # ── 3단계: Freesound API로 부족분 채우기 ──────────────
        collected = list(local_files)
        seen_ids = set()

        for query in queries:
            if len(collected) >= needed:
                break
            # page_size를 넉넉하게 잡아야 used 필터 후에도 충분히 남음
            results = self.search(query, page_size=count_per_query * 4)
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

        log.info(f"Total sounds collected: {len(collected)} (local: {len(local_files)}, api: {len(collected) - len(local_files)})")
        return collected