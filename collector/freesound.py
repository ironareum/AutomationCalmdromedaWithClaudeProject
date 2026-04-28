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
2026.04.04 feat: 3레이어 사운드 구조 (main/sub/point) + 볼륨 랜덤화 + calm 쿼리 강화
2026.04.04 feat: used_assets 신규 세션 quality=pending 기본값 설정
2026.04.05 feat: category 필드 추가, 순차 카테고리 선택 로직 완성
2026.04.11 feat: 레이어 수집 결과 1개 이하면 추가 수집으로 최소 2개 보장

"""

import re
import shutil
import subprocess
import time
import json
import logging
import requests
from pathlib import Path

log = logging.getLogger(__name__)

LUFS_SOURCE_MIN = -35.0  # ffmpeg_producer.py와 동일 기준


def _measure_lufs_quick(audio_path: Path) -> float | None:
    """ffmpeg loudnorm 분석 모드로 소스 LUFS 측정 (수집 단계 스크리닝용, 처음 60초 샘플링)"""
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        "-t", "60",
        "-i", str(audio_path),
        "-af", "loudnorm=I=-18:TP=-1.5:LRA=11:print_format=json",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        match = re.search(r'\{[^{}]+\}', result.stderr, re.DOTALL)
        if match:
            data = json.loads(match.group())
            val = data.get("input_i", "")
            if val and val not in ("-inf", "+inf"):
                return round(float(val), 1)
    except Exception as e:
        log.warning(f"LUFS 측정 실패 ({audio_path.name}): {e}")
    return None


def _save_source(work_dir: Path, kind: str, file_id: str, creator: str):
    """work_dir/sources.json 에 크리에이터 정보 누적 저장"""
    path = work_dir / "sources.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        data.setdefault(kind, {})[file_id] = {"creator": creator}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning(f"sources.json 저장 실패: {e}")


# 사용한 asset 관리
USED_ASSETS_FILE  = Path(__file__).parent.parent / "used_assets.json"
BLACKLIST_FILE    = Path(__file__).parent.parent / "blacklist.json"

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


def load_blacklist() -> set:
    """blacklist.json에서 블랙리스트 파일명 집합 로드"""
    if not BLACKLIST_FILE.exists():
        return set()
    data = json.loads(BLACKLIST_FILE.read_text(encoding="utf-8"))
    return set(data.get("sounds", []))


def save_blacklist(names: set):
    """블랙리스트 저장"""
    existing = load_blacklist()
    merged = existing | names
    data = {
        "sounds": sorted(merged),
        "description": "Freesound 수집 시 이 파일들은 스킵",
    }
    BLACKLIST_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.info(f"블랙리스트 업데이트: {len(merged)}개 ({len(names - existing)}개 신규)")


def save_used_assets(data: dict):
    USED_ASSETS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def register_used_session(session_id: str, title: str,
                           sound_files: list, video_files: list,
                           category: str = "",
                           audio_lufs: float | None = None,
                           source_lufs: dict | None = None,
                           excluded_sources: dict | None = None):
    """
    파이프라인 완료 후 실제 사용한 소스를 used_assets.json에 등록
    키: session_id (output 폴더명과 동일)
    """
    from datetime import datetime

    data = load_used_assets()

    data[session_id] = {
        "title":            title,
        "category":         category,
        "created_at":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "quality":          "pending",
        "sounds":           [f.name for f in sound_files],
        "videos":           [f.name for f in video_files],
        "audio_lufs":       audio_lufs,
        "source_lufs":      source_lufs or {},
        "excluded_sources": excluded_sources or {},
    }
    save_used_assets(data)
    lufs_str = f"{audio_lufs} LUFS" if audio_lufs is not None else "측정없음"
    excl_str = f", 제외={list(excluded_sources.keys())}" if excluded_sources else ""
    log.info(f"used_assets 등록: [{session_id}] sounds={len(sound_files)}, videos={len(video_files)}, {lufs_str}{excl_str}")


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
        self.used      = load_used_assets()
        self.blacklist = load_blacklist()
        self.local     = LocalSoundCollector(work_dir, session_id=session_id)
        if self.blacklist:
            log.info(f"블랙리스트 로드: {len(self.blacklist)}개 파일 스킵 예정")
        log.info(f"Used sessions so far: {len(self.used)} — {list(self.used.keys())[-3:] if self.used else []}")

    def _used_sound_names(self) -> set:
        """이미 사용된 사운드 파일명 집합 반환 (블랙리스트 포함)"""
        names = set()
        for entry in self.used.values():
            # quality=bad인 세션은 sounds 재사용 허용 (스킵 안 함)
            if entry.get("quality") == "bad":
                continue
            names.update(entry.get("sounds", []))
        # 블랙리스트는 항상 스킵
        names.update(self.blacklist)
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
                "fields":    "id,name,duration,license,previews,avg_rating,num_downloads,tags,description,username",
                "filter":    '+(license:"Creative Commons 0" OR license:"Attribution") avg_rating:[4 TO *] -tag:white-noise -tag:"white noise" -tag:static -tag:hiss -tag:"pink noise" -tag:wind-noise -tag:"wind noise" -tag:noisy',
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
                    and r.get("name", "") not in self.blacklist
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
            _save_source(self.sound_dir.parent, "sounds", str(sound["id"]), sound.get("username", ""))
            return dest
        except Exception as e:
            log.error(f"Sound download failed {sound['id']}: {e}")
            return None

    def collect(self, queries: list[str], count_per_query: int = 3, skip_local: bool = False, concept: dict = None, sound_layers: dict = None) -> list[Path]:
        """
        1단계: 로컬 assets/sounds/ 폴더 확인
        2단계: 로컬 부족하면 Freesound API 시도
        3단계: API도 안 되면 로컬 파일만으로 진행
        """
        # sound_layers가 있으면 메인/서브/포인트 구조로 각각 수집
        if sound_layers and not skip_local:
            result = self._collect_by_layers(sound_layers, concept)
            # 최소 2개 음원 보장: 1개 이하면 sub 쿼리로 추가 수집 시도
            if len(result) < 2:
                log.warning(f"레이어 수집 결과 {len(result)}개 — 최소 2개 확보 재시도...")
                result = self._supplement_sounds(result, sound_layers, target=2)
            return result

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
        sound_meta = {}  # 파일명 → {tags, description}

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
                    # 메타데이터 보존 (AI 검증용)
                    sound_meta[path.name] = {
                        "tags": sound.get("tags", []),
                        "description": (sound.get("description", "") or "")[:200],
                    }
                    seen_ids.add(sound["id"])
                    downloaded += 1

                time.sleep(0.3)  # API rate limit 방지

        # AI 검증: concept이 있으면 파일명+태그+description 기반으로 부적합 파일 제거
        if concept and collected:
            collected = self._ai_filter_sounds(collected, concept, sound_meta)

        log.info(f"Total sounds collected: {len(collected)} (local: {len(local_files)}, api: {len(collected) - len(local_files)})")
        return collected

    def _ai_filter_sounds(self, sound_files: list, concept: dict, sound_meta: dict = None) -> list:
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

        category   = concept.get("category", "")
        title      = concept.get("title", "")
        mood       = concept.get("mood", "")
        sound_hint = concept.get("sound_hint", "")

        # 파일 정보 구성 (파일명 + tags + description)
        sound_meta = sound_meta or {}
        file_info = []
        for p in sound_files:
            meta = sound_meta.get(p.name, {})
            tags = ", ".join(meta.get("tags", [])[:8]) if meta.get("tags") else "태그 없음"
            desc = meta.get("description", "")[:100] if meta.get("description") else ""
            line = f"- {p.name}"
            if tags != "태그 없음":
                line += f" [태그: {tags}]"
            if desc:
                line += f" [설명: {desc}]"
            file_info.append(line)

        files_str = "\n".join(file_info)

        prompt = f"""너는 힐링/ASMR 유튜브 채널의 사운드 큐레이터야.
채널 목적: 강박, 불안, 공황, 우울이 있는 사람들을 위한 치유 컨텐츠. 차분하고 마음을 명상 상태로 만드는 힐링 사운드.

[오늘 영상 정보]
- 카테고리: {category}
- 제목: {title}
- 분위기: {mood}{f"{chr(10)}- 사운드 특성: {sound_hint}" if sound_hint else ""}

[다운받은 사운드 파일들]
{files_str}

위 파일들을 판단해서 치유/힐링 영상에 적합한 파일만 선택해줘.

[선택 기준 — 이 기준에 맞는 파일만 keep]
✓ 오늘 영상 카테고리({category})와 소리가 일치
✓ 차분하고 평온하며 마음을 안정시키는 소리
✓ 강박/불안/공황/우울이 있는 사람에게 안전한 소리
✓ tags나 description에 ambient, calm, gentle, peaceful, soft, relaxing, nature 같은 단어 있으면 우선 선택

[제거 기준 — 이 기준에 해당하면 반드시 제거]
✗ 파일명/tags/description에 자극적 소리 암시
  (howling, storm, crash, war, battle, scream, horror, intense, dramatic, loud, aggressive 등)
✗ 카테고리와 전혀 다른 소리
  (비행기 컨셉인데 waves/birds, 수중 컨셉인데 rain/wind 등)
✗ 긴장감/공포감/불쾌감을 줄 수 있는 소리
✗ 반복적이고 자극적인 기계음, 경보음, 사이렌
✗ 화이트 노이즈, 핑크 노이즈 — 파일명/tags에 whitenoise, white noise, white_noise, pink noise, pink_noise 포함 시 즉시 제거
  (브라운 노이즈만 예외적으로 허용)
✗ 하이 프리퀀시 / 하이 노이즈 — 귀에 거슬리는 고주파 성분 포함 파일 제거
  파일명/tags에 hiss, static, noise, high frequency, harsh, shrill, shriek, screech 포함 시 제거
  강한 바람 소리 (wind gust, howl, blowing, strong wind 등) — 배경 바람은 허용, 강한 돌풍은 제거
✗ 음악적 요소 포함 (멜로디, 비트, 리듬, 악기 연주 등)
  (music, beat, melody, funk, loop with melody, song 등)

[예외 처리]
- 모든 파일이 부적합해도 반드시 가장 나은 3개 선택 (파일이 없으면 영상 제작 불가)
- 파일명만으로 판단 어려울 때는 tags와 description 우선 참고
- tags/description 없는 파일은 파일명으로만 판단

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

            # 실제 존재하는 파일명만 매칭 (AI가 잘못된 파일명 반환 대비)
            valid_names = {f.name for f in sound_files}
            matched_names = keep_names & valid_names
            unmatched = keep_names - valid_names
            if unmatched:
                log.warning(f"AI가 존재하지 않는 파일 반환 (무시): {unmatched}")

            filtered = [f for f in sound_files if f.name in matched_names]
            removed  = [f.name for f in sound_files if f.name not in matched_names]

            if removed:
                log.info(f"AI 사운드 검증 — 제거: {removed}")
                log.info(f"AI 사운드 검증 — 이유: {reason}")

            # AI 결정을 항상 존중: 제거 대상 파일 즉시 삭제 (폴백 없음)
            for f in sound_files:
                if f.name not in keep_names:
                    try:
                        f.unlink()
                    except Exception:
                        pass

            if len(filtered) < 3:
                log.warning(f"AI 검증 후 파일 부족 ({len(filtered)}개) — AI 필터 결과 그대로 사용")

            return filtered

        except Exception as e:
            log.error(f"AI 사운드 검증 실패: {e} — 원본 사용")
            return sound_files
    def _collect_by_layers(self, sound_layers: dict, concept: dict = None) -> list[Path]:
        """
        인트로/메인/서브/포인트 구조로 각 레이어별 최적 파일 1개씩 수집
        - intro: 기내 안내방송 등 1회성 인트로 → 5초 이상, intro_ prefix 저장
        - main:  앰비언스 핵심음 → 60초 이상
        - sub:   배경 보완음 → 10초 이상
        - point: 포인트 효과음 → 10초 이상
        """
        result = []
        sound_meta = {}
        selected_names: set[str] = set()  # 레이어 간 중복 방지
        layer_names = ["intro", "main", "sub", "point"]

        for layer in layer_names:
            queries = sound_layers.get(layer, [])
            if not queries:
                continue

            # 레이어별 최소 길이
            if layer == "main":
                min_dur = 60
            elif layer == "intro":
                min_dur = 5
            else:
                min_dur = 10

            found = None
            for query in queries:
                if found:
                    break
                results = self.search(query, page_size=12)
                for sound in results:
                    if sound.get("duration", 0) < min_dur:
                        continue
                    path = self.download(sound)
                    if path:
                        # 레이어 간 중복 방지
                        if path.name in selected_names:
                            log.warning(f"레이어 중복 스킵 [{layer}]: {path.name}")
                            path.unlink(missing_ok=True)
                            continue
                        # LUFS 스크리닝: -35 미만 소스는 수집 단계에서 즉시 교체
                        lufs = _measure_lufs_quick(path)
                        if lufs is not None and lufs < LUFS_SOURCE_MIN:
                            log.warning(f"소스 LUFS 미달 ({lufs} < {LUFS_SOURCE_MIN}) — 스킵: {path.name}")
                            path.unlink(missing_ok=True)
                            time.sleep(0.3)
                            continue
                        # intro 파일: ffmpeg에서 1회 재생 구분을 위해 prefix 추가
                        if layer == "intro":
                            intro_path = path.parent / f"intro_{path.name}"
                            path.rename(intro_path)
                            path = intro_path
                        selected_names.add(path.name)
                        found = path
                        sound_meta[path.name] = {
                            "tags": sound.get("tags", []),
                            "description": (sound.get("description", "") or "")[:200],
                            "layer": layer,
                        }
                        break
                    time.sleep(0.3)

            if found:
                result.append(found)
                log.info(f"레이어 [{layer}] 수집 완료: {found.name}")
            else:
                log.warning(f"레이어 [{layer}] 수집 실패 — 쿼리: {queries[:2]}")

        # AI 검증 (intro 파일 제외하고 검증)
        non_intro = [f for f in result if not f.name.startswith("intro_")]
        intro     = [f for f in result if f.name.startswith("intro_")]
        if concept and non_intro:
            non_intro = self._ai_filter_sounds(non_intro, concept, sound_meta)
        result = intro + non_intro

        log.info(f"레이어 구조 수집 완료: {len(result)}개 (intro: {len(intro)}개)")
        return result

    def _supplement_sounds(self, existing: list[Path], sound_layers: dict, target: int = 2) -> list[Path]:
        """
        레이어 수집 결과가 target개 미만일 때 sub → main → point 쿼리 순으로 추가 수집.
        AI 필터 없이 기본 품질 기준(10초 이상)만 적용 (이미 필터링 후 부족한 상태이므로).
        """
        result       = list(existing)
        existing_names = {f.name for f in result}

        for layer in ["sub", "main", "point"]:
            if len(result) >= target:
                break
            queries = sound_layers.get(layer, [])
            for query in queries:
                if len(result) >= target:
                    break
                sounds = self.search(query, page_size=15)
                for sound in sounds:
                    if len(result) >= target:
                        break
                    if sound.get("duration", 0) < 10:
                        continue
                    path = self.download(sound)
                    if path and path.name not in existing_names:
                        lufs = _measure_lufs_quick(path)
                        if lufs is not None and lufs < LUFS_SOURCE_MIN:
                            log.warning(f"추가수집 LUFS 미달 ({lufs}) — 스킵: {path.name}")
                            path.unlink(missing_ok=True)
                            time.sleep(0.3)
                            continue
                        result.append(path)
                        existing_names.add(path.name)
                        log.info(f"추가 수집 [{layer}]: {path.name}")
                        break
                    time.sleep(0.3)

        if len(result) < target:
            log.warning(f"추가 수집 후에도 {len(result)}개 — {target}개 확보 실패")
        else:
            log.info(f"최소 {target}개 확보 완료: {len(result)}개")
        return result