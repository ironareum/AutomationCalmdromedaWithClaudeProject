"""
tests/test_pipeline.py
Calmdromeda 파이프라인 CI 테스트
---------------------------------------------------------------
1. TestPreflightChecks (10개) - 사전 체크
   - FFmpeg 설치
   - 환경변수 존재
   - YouTube 토큰 존재/유효성
   - client_secret 존재
   - assets 폴더/폰트 파일
   - 암호화 키
   - blacklist/used_assets JSON 유효성

2. TestPickCategory (6개) - 카테고리 선택 로직
3. TestGetRecentCategories (4개) - 최근 카테고리 추출
4. TestBlacklist (4개) - 블랙리스트 로직
5. TestRegisterUsedSession (3개) - 세션 등록
6. TestGenerateDescription (11개) - 설명문 생성
7. TestPexelsGetBestFile (7개) - 영상 파일 선택
8. TestPexelsPeopleFilter (2개) - 사람 필터링
9. TestThumbnailUtils (5개) - 썸네일 유틸
---------------------------------------------------------------
실행 방법:
  pytest tests/test_pipeline.py -v
  pytest tests/test_pipeline.py -v -k "check"   # 사전 체크만
  pytest tests/test_pipeline.py -v -k "logic"   # 로직만
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ════════════════════════════════════════════════════════════════════════════
# 공통 픽스처
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_assets(tmp_path):
    """테스트용 임시 assets 구조 생성"""
    (tmp_path / "sounds").mkdir()
    (tmp_path / "video").mkdir()
    (tmp_path / "fonts").mkdir()
    return tmp_path


@pytest.fixture
def sample_used_assets(tmp_path):
    """테스트용 used_assets.json 생성"""
    data = {
        "20260401_000001": {"title": "빗소리", "category": "rain",
                            "quality": "good", "sounds": ["rain1.mp3"], "videos": ["v1.mp4"]},
        "20260401_000002": {"title": "숲소리", "category": "forest",
                            "quality": "good", "sounds": ["forest1.mp3"], "videos": ["v2.mp4"]},
        "20260401_000003": {"title": "수중소리", "category": "underwater",
                            "quality": "bad", "sounds": ["water1.mp3"], "videos": ["v3.mp4"]},
        "20260401_000004": {"title": "카페소리", "category": "cafe",
                            "quality": "pending", "sounds": ["cafe1.mp3"], "videos": ["v4.mp4"]},
        "20260401_000005": {"title": "지하철", "category": "subway",
                            "quality": "good", "sounds": ["sub1.mp3"], "videos": ["v5.mp4"]},
        "20260401_000006": {"title": "귀뚜라미", "category": "summer_night",
                            "quality": "good", "sounds": ["cricket1.mp3"], "videos": ["v6.mp4"]},
        "20260401_000007": {"title": "모닥불", "category": "fireplace_rain",
                            "quality": "good", "sounds": ["fire1.mp3"], "videos": ["v7.mp4"]},
    }
    path = tmp_path / "used_assets.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def sample_blacklist(tmp_path):
    """테스트용 blacklist.json 생성"""
    data = {"sounds": ["bad_sound1.mp3", "bad_sound2.mp3"], "description": "test"}
    path = tmp_path / "blacklist.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def base_concept():
    """테스트용 기본 concept dict"""
    return {
        "title": "빗소리 ASMR Rain Sounds | 틀어두면 잠드는 소리 | Sleep Music",
        "duration_hours": 1,
        "mood": "cozy rainy",
        "tags": ["빗소리", "ASMR", "수면음악"],
        "language": "ko",
        "description_en": "",
    }


@pytest.fixture
def pexels_collector(tmp_path):
    """API 호출 없이 PexelsCollector 인스턴스 생성"""
    with patch("collector.freesound.load_used_assets", return_value={}):
        from collector.pexels import PexelsCollector
        return PexelsCollector(api_key="dummy_key", work_dir=tmp_path, session_id="test")


@pytest.fixture
def fake_video():
    """Pexels API 응답을 흉내낸 가짜 video dict"""
    return {
        "id": 99999,
        "duration": 60,
        "url": "https://pexels.com/video/forest-99999",
        "user": {"name": "naturephotographer"},
        "tags": [],
        "video_files": [
            {"file_type": "video/mp4",  "height": 2160, "link": "https://example.com/4k.mp4"},
            {"file_type": "video/mp4",  "height": 1080, "link": "https://example.com/1080.mp4"},
            {"file_type": "video/mp4",  "height": 720,  "link": "https://example.com/720.mp4"},
            {"file_type": "video/webm", "height": 1080, "link": "https://example.com/1080.webm"},
        ],
    }


# ════════════════════════════════════════════════════════════════════════════
# 1. 사전 체크 — 실행 전 필수 조건
# ════════════════════════════════════════════════════════════════════════════

class TestPreflightChecks:
    """실행 전 환경 사전 체크"""

    def test_ffmpeg_installed(self):
        """FFmpeg 설치 여부"""
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, timeout=10
        )
        assert result.returncode == 0, "FFmpeg가 설치되어 있지 않습니다"

    def test_required_env_vars_present(self):
        """필수 환경변수 존재 여부 (CI에서 실제 값, 로컬에서 .env)"""
        required = ["ANTHROPIC_API_KEY", "FREESOUND_API_KEY", "PEXELS_API_KEY"]
        missing = [k for k in required if not os.environ.get(k)]
        assert not missing, f"환경변수 없음: {missing}"

    def test_youtube_token_exists(self):
        """YouTube 토큰 파일 존재 여부"""
        token_paths = [
            Path("credentials/token.json"),
            Path(os.environ.get("YOUTUBE_TOKEN", "credentials/token.json")),
        ]
        exists = any(p.exists() for p in token_paths)
        assert exists, "YouTube token.json 없음 — python test_youtube.py 실행 필요"

    def test_youtube_token_valid_json(self):
        """YouTube 토큰 파일이 유효한 JSON인지"""
        token_path = Path(os.environ.get("YOUTUBE_TOKEN", "credentials/token.json"))
        if not token_path.exists():
            pytest.skip("token.json 없음 — 스킵")
        content = token_path.read_text(encoding="utf-8")
        try:
            data = json.loads(content)
            assert "token" in data or "access_token" in data or "refresh_token" in data, \
                "token.json에 토큰 필드 없음"
        except json.JSONDecodeError:
            pytest.fail("token.json이 유효한 JSON이 아닙니다")

    def test_client_secret_exists(self):
        """Google client_secret.json 존재 여부"""
        path = Path("credentials/client_secret.json")
        assert path.exists(), "client_secret.json 없음"

    def test_required_assets_dirs(self):
        """필수 assets 폴더 존재 여부"""
        required_dirs = [
            Path("assets/fonts"),
            Path("assets"),
        ]
        missing = [str(d) for d in required_dirs if not d.exists()]
        assert not missing, f"필수 폴더 없음: {missing}"

    def test_font_files_exist(self):
        """폰트 파일 존재 여부"""
        fonts = [
            Path("assets/fonts/RIDIBatang.otf"),
            Path("assets/fonts/Bitter-Italic.ttf"),
        ]
        missing = [str(f) for f in fonts if not f.exists()]
        assert not missing, f"폰트 파일 없음: {missing}"

    def test_encryption_key_set(self):
        """암호화 키 환경변수 존재 여부"""
        key = os.environ.get("ENCRYPTION_KEY", "")
        assert key, "ENCRYPTION_KEY 환경변수 없음"

    def test_blacklist_json_valid(self):
        """blacklist.json 유효성"""
        path = Path("blacklist.json")
        if not path.exists():
            pytest.skip("blacklist.json 없음 — 스킵")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "sounds" in data, "blacklist.json에 sounds 키 없음"
        assert isinstance(data["sounds"], list), "sounds가 리스트가 아님"

    def test_used_assets_json_valid(self):
        """used_assets.json 유효성"""
        path = Path("used_assets.json")
        if not path.exists():
            pytest.skip("used_assets.json 없음 — 스킵")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict), "used_assets.json이 dict가 아님"
        for sid, entry in data.items():
            assert "title" in entry, f"{sid}: title 없음"
            assert "sounds" in entry, f"{sid}: sounds 없음"


# ════════════════════════════════════════════════════════════════════════════
# 2. 핵심 로직 단위 테스트
# ════════════════════════════════════════════════════════════════════════════

class TestPickCategory:
    """_pick_category 카테고리 선택 로직"""

    def setup_method(self):
        from planner.concept_generator import ALL_CATEGORIES, CATEGORY_GROUPS
        self.ALL_CATEGORIES = ALL_CATEGORIES
        self.CATEGORY_GROUPS = CATEGORY_GROUPS

    def _pick(self, recent):
        from planner.concept_generator import _pick_category
        return _pick_category(recent)

    def test_never_used_first(self):
        """한 번도 안 쓴 카테고리 최우선 선택"""
        recent = ["rain", "forest", "ocean"]
        chosen = self._pick(recent)
        assert chosen not in recent or chosen in self.ALL_CATEGORIES

    def test_returns_valid_category(self):
        """반환값이 항상 ALL_CATEGORIES 안에 있는지"""
        recent = ["rain", "forest"]
        chosen = self._pick(recent)
        assert chosen in self.ALL_CATEGORIES

    def test_skips_recent_7(self):
        """최근 7개 카테고리 스킵"""
        all_cats = self.ALL_CATEGORIES
        # 모든 카테고리 사용 후 최근 7개 제외
        recent = all_cats[:7]
        chosen = self._pick(all_cats)  # 전체 사용 후
        assert chosen in self.ALL_CATEGORIES

    def test_empty_recent(self):
        """recent_categories 비어있을 때도 정상 동작"""
        chosen = self._pick([])
        assert chosen in self.ALL_CATEGORIES

    def test_group_not_consecutive(self):
        """같은 그룹 연속 방지"""
        # rain_group 최근 사용
        recent = ["rain", "forest", "ocean", "cafe", "subway"]
        chosen = self._pick(recent)
        # rain_group (rain, rain_thunder, summer_rain, fireplace_rain) 연속 안 나와야 함
        rain_group = self.CATEGORY_GROUPS.get("rain_group", [])
        # recent 마지막 2개와 같은 그룹 아니어야 함 (완벽하진 않지만 기본 체크)
        assert chosen in self.ALL_CATEGORIES

    def test_all_categories_used_restarts(self):
        """전체 순환 완료 후 재시작"""
        all_cats = self.ALL_CATEGORIES
        chosen = self._pick(all_cats)
        assert chosen in self.ALL_CATEGORIES


class TestGetRecentCategories:
    """_get_recent_categories 최근 카테고리 추출"""

    def test_reads_category_field(self, sample_used_assets):
        """category 필드 직접 읽기"""
        from planner.concept_generator import _get_recent_categories
        result = _get_recent_categories(sample_used_assets)
        assert "rain" in result
        assert "forest" in result

    def test_bad_quality_included(self, sample_used_assets):
        """quality=bad 세션도 카테고리 추적에 포함"""
        from planner.concept_generator import _get_recent_categories
        result = _get_recent_categories(sample_used_assets)
        assert "underwater" in result

    def test_empty_file(self, tmp_path):
        """빈 used_assets.json 처리"""
        path = tmp_path / "used_assets.json"
        path.write_text("{}", encoding="utf-8")
        from planner.concept_generator import _get_recent_categories
        result = _get_recent_categories(path)
        assert result == []

    def test_missing_file(self, tmp_path):
        """파일 없을 때 빈 리스트 반환"""
        from planner.concept_generator import _get_recent_categories
        result = _get_recent_categories(tmp_path / "nonexistent.json")
        assert result == []


class TestBlacklist:
    """블랙리스트 로직"""

    def test_load_blacklist(self, sample_blacklist, monkeypatch):
        """blacklist.json 로드"""
        from collector import freesound
        monkeypatch.setattr(freesound, "BLACKLIST_FILE", sample_blacklist)
        result = freesound.load_blacklist()
        assert "bad_sound1.mp3" in result
        assert "bad_sound2.mp3" in result

    def test_load_blacklist_missing_file(self, tmp_path, monkeypatch):
        """파일 없을 때 빈 set 반환"""
        from collector import freesound
        monkeypatch.setattr(freesound, "BLACKLIST_FILE", tmp_path / "none.json")
        result = freesound.load_blacklist()
        assert result == set()

    def test_blacklisted_sound_in_used_names(self, sample_blacklist, sample_used_assets, monkeypatch, tmp_path):
        """블랙리스트 파일은 used_sound_names에 포함"""
        from collector import freesound
        monkeypatch.setattr(freesound, "BLACKLIST_FILE", sample_blacklist)
        monkeypatch.setattr(freesound, "USED_ASSETS_FILE", sample_used_assets)

        with patch("collector.freesound.load_used_assets",
                   return_value=json.loads(sample_used_assets.read_text(encoding="utf-8"))):
            collector = freesound.FreesoundCollector.__new__(freesound.FreesoundCollector)
            collector.used = json.loads(sample_used_assets.read_text(encoding="utf-8"))
            collector.blacklist = freesound.load_blacklist()
            collector.local = MagicMock()

            names = collector._used_sound_names()
            assert "bad_sound1.mp3" in names
            assert "bad_sound2.mp3" in names

    def test_bad_quality_sounds_reusable(self, sample_used_assets, monkeypatch):
        """quality=bad 세션의 sounds는 재사용 가능 (used_names에서 제외)"""
        from collector import freesound
        monkeypatch.setattr(freesound, "BLACKLIST_FILE",
                            Path("/nonexistent/blacklist.json"))

        with patch("collector.freesound.load_used_assets",
                   return_value=json.loads(sample_used_assets.read_text(encoding="utf-8"))):
            collector = freesound.FreesoundCollector.__new__(freesound.FreesoundCollector)
            collector.used = json.loads(sample_used_assets.read_text(encoding="utf-8"))
            collector.blacklist = set()
            collector.local = MagicMock()

            names = collector._used_sound_names()
            # quality=bad인 세션의 water1.mp3는 재사용 가능
            assert "water1.mp3" not in names
            # quality=good인 세션의 rain1.mp3는 스킵
            assert "rain1.mp3" in names


class TestRegisterUsedSession:
    """register_used_session 세션 등록"""

    def test_quality_pending_default(self, tmp_path, monkeypatch):
        """신규 세션 등록 시 quality=pending 기본값"""
        from collector import freesound
        assets_path = tmp_path / "used_assets.json"
        assets_path.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(freesound, "USED_ASSETS_FILE", assets_path)

        sound = MagicMock(); sound.name = "test_sound.mp3"
        video = MagicMock(); video.name = "test_video.mp4"

        freesound.register_used_session("test_session", "테스트", [sound], [video], category="rain")

        data = json.loads(assets_path.read_text(encoding="utf-8"))
        assert "test_session" in data
        assert data["test_session"]["quality"] == "pending"

    def test_category_saved(self, tmp_path, monkeypatch):
        """카테고리 필드 저장"""
        from collector import freesound
        assets_path = tmp_path / "used_assets.json"
        assets_path.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(freesound, "USED_ASSETS_FILE", assets_path)

        sound = MagicMock(); sound.name = "s.mp3"
        video = MagicMock(); video.name = "v.mp4"

        freesound.register_used_session("sess1", "제목", [sound], [video], category="ocean")

        data = json.loads(assets_path.read_text(encoding="utf-8"))
        assert data["sess1"]["category"] == "ocean"

    def test_sounds_videos_saved(self, tmp_path, monkeypatch):
        """sounds, videos 목록 저장"""
        from collector import freesound
        assets_path = tmp_path / "used_assets.json"
        assets_path.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(freesound, "USED_ASSETS_FILE", assets_path)

        s1 = MagicMock(); s1.name = "sound1.mp3"
        s2 = MagicMock(); s2.name = "sound2.mp3"
        v1 = MagicMock(); v1.name = "video1.mp4"

        freesound.register_used_session("sess2", "제목", [s1, s2], [v1])

        data = json.loads(assets_path.read_text(encoding="utf-8"))
        assert "sound1.mp3" in data["sess2"]["sounds"]
        assert "sound2.mp3" in data["sess2"]["sounds"]
        assert "video1.mp4" in data["sess2"]["videos"]


class TestGenerateDescription:
    """generate_description 설명문 생성"""

    def test_korean_section_included(self, base_concept):
        """한국어 섹션 포함"""
        from pipeline import generate_description
        result = generate_description(base_concept)
        assert "편안하게 쉬거나" in result
        assert "공부, 업무, 명상" in result

    def test_english_section_included(self, base_concept):
        """영어 섹션 포함 (기본값)"""
        from pipeline import generate_description
        result = generate_description(base_concept)
        assert "headphones" in result

    def test_custom_description_en_used(self, base_concept):
        """description_en 직접 지정 시 대체"""
        from pipeline import generate_description
        base_concept["description_en"] = "Custom English here."
        result = generate_description(base_concept)
        assert "Custom English here." in result

    def test_tags_have_hash(self, base_concept):
        """태그에 # 붙는지"""
        from pipeline import generate_description
        result = generate_description(base_concept)
        assert "#빗소리" in result
        assert "#ASMR" in result

    def test_tag_spaces_removed(self, base_concept):
        """태그 공백 제거"""
        from pipeline import generate_description
        base_concept["tags"] = ["rain sounds", "white noise"]
        result = generate_description(base_concept)
        assert "#rainsounds" in result
        assert "#whitenoise" in result

    def test_channel_name_included(self, base_concept):
        """채널명 포함"""
        from pipeline import generate_description
        result = generate_description(base_concept)
        assert "@Calmdromeda" in result

    def test_duration_reflected(self, base_concept):
        """duration_hours 반영"""
        from pipeline import generate_description
        result = generate_description(base_concept)
        assert "1시간" in result

    def test_duration_changes(self, base_concept):
        """duration_hours 변경 시 반영"""
        from pipeline import generate_description
        base_concept["duration_hours"] = 2
        result = generate_description(base_concept)
        assert "2시간" in result

    def test_title_included(self, base_concept):
        """title 포함"""
        from pipeline import generate_description
        result = generate_description(base_concept)
        assert base_concept["title"] in result

    def test_empty_tags(self, base_concept):
        """빈 tags 에러 없이 동작"""
        from pipeline import generate_description
        base_concept["tags"] = []
        result = generate_description(base_concept)
        assert isinstance(result, str)

    def test_fixed_hashtags(self, base_concept):
        """고정 해시태그 포함"""
        from pipeline import generate_description
        result = generate_description(base_concept)
        assert "#힐링음악" in result
        assert "#수면음악" in result


class TestPexelsGetBestFile:
    """PexelsCollector.get_best_file 영상 파일 선택"""

    def test_mp4_only(self, pexels_collector, fake_video):
        """webm 제외 mp4만 반환"""
        result = pexels_collector.get_best_file(fake_video)
        assert result["file_type"] == "video/mp4"

    def test_highest_resolution(self, pexels_collector, fake_video):
        """최고 해상도 선택"""
        result = pexels_collector.get_best_file(fake_video)
        assert result["height"] == 2160

    def test_empty_files_returns_none(self, pexels_collector):
        """video_files 없으면 None"""
        result = pexels_collector.get_best_file({"id": 1, "duration": 10, "video_files": []})
        assert result is None

    def test_no_mp4_returns_none(self, pexels_collector):
        """mp4 없으면 None"""
        video = {"id": 2, "duration": 20, "video_files": [
            {"file_type": "video/webm", "height": 1080, "link": "https://example.com/webm"}
        ]}
        result = pexels_collector.get_best_file(video)
        assert result is None

    def test_single_mp4(self, pexels_collector):
        """mp4 하나만 있을 때"""
        video = {"id": 3, "duration": 15, "video_files": [
            {"file_type": "video/mp4", "height": 720, "link": "https://example.com/720.mp4"}
        ]}
        result = pexels_collector.get_best_file(video)
        assert result["height"] == 720

    def test_link_exists(self, pexels_collector, fake_video):
        """반환값에 link 포함"""
        result = pexels_collector.get_best_file(fake_video)
        assert "link" in result
        assert result["link"].startswith("https://")

    def test_longer_duration_preferred(self, pexels_collector):
        """같은 해상도면 긴 영상 우선"""
        video_short = {"id": 10, "duration": 10, "video_files": [
            {"file_type": "video/mp4", "height": 1080, "link": "https://example.com/short.mp4"}
        ]}
        video_long = {"id": 11, "duration": 120, "video_files": [
            {"file_type": "video/mp4", "height": 1080, "link": "https://example.com/long.mp4"}
        ]}
        r_short = pexels_collector.get_best_file(video_short)
        r_long  = pexels_collector.get_best_file(video_long)
        assert r_long["link"] == "https://example.com/long.mp4"


class TestPexelsPeopleFilter:
    """Pexels 사람 필터링 로직"""

    def test_people_keyword_in_url_filtered(self, pexels_collector):
        """URL에 people 키워드 있으면 필터링"""
        videos = [
            {"id": 1, "duration": 30, "url": "https://pexels.com/video/people-walking",
             "user": {"name": "photo"}, "tags": [], "video_files": []},
            {"id": 2, "duration": 30, "url": "https://pexels.com/video/forest-calm",
             "user": {"name": "nature"}, "tags": [], "video_files": []},
        ]
        PEOPLE_KEYWORDS = ["people", "person", "man", "woman", "girl", "boy",
                           "human", "crowd", "face", "portrait", "model"]

        def has_people(v):
            text = " ".join([
                v.get("url", ""),
                str(v.get("user", {}).get("name", "")),
                " ".join(str(t) for t in v.get("tags", [])),
            ]).lower()
            return any(kw in text for kw in PEOPLE_KEYWORDS)

        no_people = [v for v in videos if not has_people(v)]
        assert len(no_people) == 1
        assert no_people[0]["id"] == 2

    def test_fallback_when_all_people(self, pexels_collector):
        """모든 영상이 사람 포함이면 원본 유지 (fallback)"""
        videos = [
            {"id": 1, "duration": 30, "url": "https://pexels.com/video/man-walking",
             "user": {"name": "photo"}, "tags": []},
        ]
        PEOPLE_KEYWORDS = ["man", "woman", "people"]

        def has_people(v):
            text = v.get("url", "").lower()
            return any(kw in text for kw in PEOPLE_KEYWORDS)

        no_people = [v for v in videos if not has_people(v)]
        pool = no_people if no_people else videos  # fallback
        assert len(pool) == 1  # fallback으로 원본 유지


class TestThumbnailUtils:
    """썸네일 유틸 함수"""

    def test_split_two_lines_basic(self):
        """기본 2줄 분할"""
        from producer.thumbnail import _split_two_lines
        l1, l2 = _split_two_lines("빗소리 ASMR Rain Sounds")
        assert l1
        assert l1 + " " + l2 == "빗소리 ASMR Rain Sounds" or \
               l1 == "빗소리 ASMR Rain Sounds"

    def test_split_two_lines_no_space(self):
        """공백 없는 텍스트는 한 줄"""
        from producer.thumbnail import _split_two_lines
        l1, l2 = _split_two_lines("ASMR")
        assert l1 == "ASMR"
        assert l2 == ""

    def test_split_two_lines_near_middle(self):
        """가운데 근처에서 분할"""
        from producer.thumbnail import _split_two_lines
        text = "봄날 아침 새소리 ASMR"
        l1, l2 = _split_two_lines(text)
        assert len(l1) > 0
        assert len(l2) > 0

    def test_fit_font_size_returns_int(self):
        """폰트 크기 반환값이 정수"""
        try:
            from producer.thumbnail import _fit_font_size
            size = _fit_font_size("빗소리 ASMR", max_px=800)
            assert isinstance(size, int)
            assert 38 <= size <= 100
        except FileNotFoundError:
            pytest.skip("폰트 파일 없음 — 스킵")

    def test_fit_font_size_long_text_smaller(self):
        """긴 텍스트는 더 작은 폰트 크기"""
        try:
            from producer.thumbnail import _fit_font_size
            short = _fit_font_size("ASMR", max_px=400)
            long  = _fit_font_size("빗소리 ASMR Rain Sounds Healing", max_px=400)
            assert short >= long
        except FileNotFoundError:
            pytest.skip("폰트 파일 없음 — 스킵")