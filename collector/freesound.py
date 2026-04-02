"""
Freesound.org API Collector
2026.03.26 CC0/CC BY 라이선스 자연 사운드 자동 수집
2026.03.26 API 키 발급: https://freesound.org/apiv2/apply/
2026.03.28 사용한 소스는 used_assets.json에 기록 → 다음 실행 시 자동 스킵
2026.03.28 로컬 음원 폴백: assets/sounds/{category}/ 폴더 파일 우선 사용
2026.03.29 used_assets.json 구조 변경: session_id 키 기반으로 소스 파일명 관리
2026.03.29 로컬 사용 음원 → assets/sounds/_used/ 로 자동 이동 (재사용 방지)
2026.03.29 used_assetss.json 포맷형식 변경
2026.03.29 수집소스 페이지네이션 (수집소스 고갈 방지)
2026.04.01 재사용 모드에서는 로컬 파일 무시하고 API에서만 수집
2026.04.02 feat: AI 사운드 검증 추가 (컨셉 일치율 향상), 계절 키워드 제거
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

# FFmpeg mix_sounds()에서 실제로 사용하는 최대 레이어 수
MAX_SOUND_LAYERS = 3

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
    """
    used_assets.json 로드
    구조: { "20260329_005810": { "title": "...", "created_at": "...",
                                  "sounds": [...], "videos": [...] }, ... }
    """
    if USED_ASSETS_FILE.exists():
        return json.loads(USED_ASSETS_FILE.read_text(encoding="utf-8"))
    return {}


def save_used_assets(data: dict):
    USED_ASSETS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def register_used_session(session_id: str, title: str,
                           sound_files: list, video_files: list):
    """
    파이프라인 완료 후 실제 사용한 소스를 used_assets.json에 등록
    키: session_id (output 폴더명과 동일)

    """
    from datetime import datetime

    data = load_used_assets()

    data[session_id] = {
        "title":      title,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sounds":     [f.name for f in sound_files],
        "videos":     [f.name for f in video_files],
    }
    save_used_assets(data)
    log.info(f"used_assets 등록: [{session_id}] sounds={len(sound_files)}, videos={len(video_files)}")


def is_sound_used(filename: str) -> bool:
    """파일명이 이미 사용된 소스인지 확인"""
    data = load_used_assets()
    return any(filename in entry.get("sounds", []) for entry in data.values())


def is_video_used(video_id: str) -> bool:
    """Pexels video ID가 이미 사용된 영상인지 확인 (파일명에 ID 포함)"""
    data = load_used_assets()
    return any(
        any(video_id in fname for fname in entry.get("videos", []))
        for entry in data.values()
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

        if collected:
            log.info(f"Local sounds found: {len(collected)} files")
        else:
            log.info(f"No local sounds found in assets/sounds/")

        return collected

    def move_to_used(self, sound_file: Path):
        """
        로컬 음원을 assets/sounds/_used/{session_id}/ 로 이동
        - pipeline에서 produce() 완료 후 실제 사용한 파일에 대해서만 호출
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
        log.info(f"Used sessions so far: {len(self.used)} — {list(self.used.keys())[-3:] if self.used else []}")

    def _used_sound_names(self) -> set:
        """이미 사용된 사운드 파일명 집합 반환"""
        names = set()
        for entry in self.used.values():
            names.update(entry.get("sounds", []))
        return names

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

    def search(self, query: str, page_size: int = 15,
               max_pages: int = 5) -> list[dict]:
        """
        페이지네이션으로 fresh 결과가 나올 때까지 탐색
        - page 1이 전부 used여도 page 2, 3... 으로 자동 진행
        - max_pages: 최대 탐색 페이지 수 (API 과호출 방지)
        """
        used_names = self._used_sound_names()
        fresh_all  = []

        for page in range(1, max_pages + 1):
            params = {
                "query":     query,
                "page_size": page_size,
                "page":      page,
                "fields":    "id,name,duration,license,previews,avg_rating,num_downloads,tags,description",
                "filter":    'license:"Creative Commons 0" OR license:"Attribution"',
                "sort":      "downloads_desc",
                "token":     self.api_key,
            }
            try:
                resp = requests.get(
                    f"{self.BASE_URL}/search/text/", params=params, timeout=15
                )
                resp.raise_for_status()
                data    = resp.json()
                results = data.get("results", [])

                if not results:
                    # 더 이상 결과 없음
                    break

                fresh = [
                    r for r in results
                    if not any(str(r["id"]) in name for name in used_names)
                ]
                skipped = len(results) - len(fresh)

                if page == 1 or skipped > 0 or fresh:
                    log.info(
                        f"Freesound '{query}' p{page}: "
                        f"{len(results)} found / {skipped} skipped / {len(fresh)} fresh"
                    )

                fresh_all.extend(fresh)

                # 충분히 모았거나 다음 페이지 없으면 중단
                if len(fresh_all) >= page_size:
                    break
                if not data.get("next"):
                    break

            except Exception as e:
                log.error(f"Freesound search failed '{query}' p{page}: {e}")
                break

        return fresh_all

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
            # 사용 기록은 pipeline._cleanup_assets() 완료 후 register_used_session()으로 일괄 등록
            return dest
        except Exception as e:
            log.error(f"Sound download failed {sound['id']}: {e}")
            return None

    def collect(self, queries: list[str], count_per_query: int = 3, skip_local: bool = False, concept: dict = None) -> list[Path]:
        """
        1단계: 로컬 assets/sounds/ 폴더 확인
        2단계: 로컬 부족하면 Freesound API 시도
        3단계: API도 안 되면 로컬 파일만으로 진행
        """
        # 실제 사용하는 레이어는 MAX_SOUND_LAYERS(3)개
        # 유효하지 않은 파일 대비 여유분 확보 (최소 5개)
        needed = max(MAX_SOUND_LAYERS + 2, int(MAX_SOUND_LAYERS * 1.5))

        # ── 1단계: 로컬 음원 수집 (skip_local=True면 스킵) ────
        if skip_local:
            log.info("skip_local=True — 로컬 음원 무시, API에서만 수집")
            local_files = []
        else:
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

        # AI 검증: concept이 있으면 파일명+태그 기반으로 부적합 파일 제거
        if concept and collected:
            collected = self._ai_filter_sounds(collected, concept)

        log.info(f"Total sounds collected: {len(collected)} (local: {len(local_files)}, api: {len(collected) - len(local_files)})")
        return collected

    def _ai_filter_sounds(self, sound_files: list, concept: dict) -> list:
        """
        다운받은 파일명+Freesound 메타데이터 기반으로 AI가 컨셉 부적합 파일 제거
        """
        import anthropic, os
        from dotenv import load_dotenv
        load_dotenv()

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            log.warning("ANTHROPIC_API_KEY 없음 — AI 사운드 검증 스킵")
            return sound_files

        category = concept.get("category", "")
        title = concept.get("title", "")
        mood = concept.get("mood", "")

        # 파일 정보 구성
        file_info = []
        for p in sound_files:
            file_info.append(f"- {p.name}")

        files_str = "\n".join(file_info)

        prompt = f"""너는 힐링/ASMR 유튜브 채널의 사운드 큐레이터야.
채널 목적: 강박, 불안, 공황, 우울이 있는 사람들을 위한 치유 컨텐츠. 차분하고 마음을 명상 상태로 만드는 힐링 사운드.

[오늘 영상 정보]
- 카테고리: {category}
- 제목: {title}
- 분위기: {mood}

[다운받은 사운드 파일들]
{files_str}

위 파일들 중 영상 컨셉과 잘 맞고 치유/힐링에 적합한 파일만 선택해줘.
제거 기준:
1. 파일명에 폭발적/자극적 소리 암시 (howling, storm, crash, war, battle, scream, horror 등)
2. 컨셉과 전혀 다른 카테고리 소리 (비행기 컨셉인데 lake waves 등)
3. 치유/평온함 보다는 긴장감/공포감을 주는 소리

반드시 최소 3개는 선택해야 함. 모두 부적합해도 가장 나은 3개 선택.

JSON 형식으로만 응답:
{{
  "keep": ["파일명1.mp3", "파일명2.mp3", ...],
  "reason": "선택 이유 한 줄"
}}"""

        try:
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = message.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            result = json.loads(raw.strip())
            keep_names = set(result.get("keep", []))
            reason = result.get("reason", "")

            filtered = [f for f in sound_files if f.name in keep_names]
            removed = [f.name for f in sound_files if f.name not in keep_names]

            if removed:
                log.info(f"AI 사운드 검증 — 제거: {removed}")
                log.info(f"AI 사운드 검증 — 이유: {reason}")
                # 제거된 파일 삭제
                for f in sound_files:
                    if f.name not in keep_names:
                        try:
                            f.unlink()
                        except Exception:
                            pass

            if len(filtered) < 3:
                log.warning(f"AI 검증 후 파일 부족 ({len(filtered)}개) — 원본 유지")
                return sound_files

            return filtered

        except Exception as e:
            log.error(f"AI 사운드 검증 실패: {e} — 원본 사용")
            return sound_files