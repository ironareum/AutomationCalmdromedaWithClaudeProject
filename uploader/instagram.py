"""
Instagram Platform API Uploader
2026.04.13 신규: 썸네일 이미지 게시 (YouTube 영상 홍보)

[사전 준비]
1. Meta Developer Console → Calmdromeda 앱 → Instagram 제품 설정
2. Graph API Explorer → Instagram 장기 액세스 토큰 발급 (60일)
3. imgbb.com → 무료 API 키 발급
4. .env / GitHub Secrets에 아래 항목 설정:
   - INSTAGRAM_ACCESS_TOKEN
   - INSTAGRAM_USER_ID  (예: 27312581898330133)
   - IMGBB_API_KEY

[토큰 갱신]
- 장기 토큰은 60일 유효
- 파이프라인 실행 시 자동으로 갱신 시도 (refresh_token 호출)
- 갱신된 토큰은 로그에 출력 → GitHub Secret 수동 업데이트 필요
"""

import logging
import time
import requests
from pathlib import Path

log = logging.getLogger(__name__)

GRAPH_URL = "https://graph.instagram.com/v25.0"
IMGBB_URL = "https://api.imgbb.com/1/upload"


class InstagramUploader:

    def __init__(self, access_token: str, user_id: str, imgbb_api_key: str = ""):
        self.access_token = access_token
        self.user_id = user_id
        self.imgbb_api_key = imgbb_api_key

    # ── 이미지 호스팅 ────────────────────────────────────────────────────

    def _host_image(self, image_path: Path) -> str | None:
        """imgbb에 이미지 업로드 후 공개 URL 반환"""
        if not self.imgbb_api_key:
            log.error("IMGBB_API_KEY 없음 — Instagram 이미지 업로드 불가")
            return None

        try:
            with open(image_path, "rb") as f:
                resp = requests.post(
                    IMGBB_URL,
                    params={"key": self.imgbb_api_key},
                    files={"image": f},
                    timeout=30,
                )
            resp.raise_for_status()
            url = resp.json()["data"]["url"]
            log.info(f"imgbb 업로드 완료: {url}")
            return url
        except Exception as e:
            log.error(f"imgbb 업로드 실패: {e}")
            return None

    # ── Instagram API ────────────────────────────────────────────────────

    def _create_media_container(self, image_url: str, caption: str) -> str | None:
        """미디어 컨테이너 생성 → creation_id 반환"""
        try:
            resp = requests.post(
                f"{GRAPH_URL}/{self.user_id}/media",
                data={
                    "image_url": image_url,
                    "media_type": "IMAGE",
                    "caption": caption,
                    "access_token": self.access_token,
                },
                timeout=30,
            )
            if not resp.ok:
                log.error(f"미디어 컨테이너 생성 실패: {resp.status_code} | 응답: {resp.text}")
                return None
            creation_id = resp.json()["id"]
            log.info(f"미디어 컨테이너 생성: {creation_id}")
            return creation_id
        except Exception as e:
            log.error(f"미디어 컨테이너 생성 실패: {e}")
            return None

    def _wait_for_media_ready(self, creation_id: str, max_wait: int = 60) -> bool:
        """미디어 처리 완료 대기 (최대 max_wait초, 5초 간격)"""
        for _ in range(max_wait // 5):
            try:
                resp = requests.get(
                    f"{GRAPH_URL}/{creation_id}",
                    params={"fields": "status_code", "access_token": self.access_token},
                    timeout=10,
                )
                status = resp.json().get("status_code", "")
                if status == "FINISHED":
                    return True
                if status == "ERROR":
                    log.error(f"미디어 처리 오류: {resp.json()}")
                    return False
                time.sleep(5)
            except Exception as e:
                log.warning(f"상태 확인 중 오류: {e}")
                time.sleep(5)
        log.error("미디어 처리 타임아웃")
        return False

    def _publish_media(self, creation_id: str) -> dict | None:
        """미디어 게시"""
        try:
            resp = requests.post(
                f"{GRAPH_URL}/{self.user_id}/media_publish",
                data={
                    "creation_id": creation_id,
                    "access_token": self.access_token,
                },
                timeout=30,
            )
            resp.raise_for_status()
            post_id = resp.json()["id"]
            log.info(f"Instagram 게시 완료: post_id={post_id}")
            return {"post_id": post_id}
        except Exception as e:
            log.error(f"Instagram 게시 실패: {e}")
            return None

    # ── 공개 인터페이스 ──────────────────────────────────────────────────

    def post(self, image_path: Path, caption: str) -> dict | None:
        """
        썸네일 이미지를 Instagram에 게시

        Args:
            image_path: 썸네일 이미지 파일 경로
            caption:    게시물 캡션 (해시태그 포함)

        반환: {"post_id": "..."} 또는 None (실패 시)
        """
        if not image_path.exists():
            log.error(f"이미지 파일 없음: {image_path}")
            return None

        # 1. 이미지를 공개 URL에 호스팅
        image_url = self._host_image(image_path)
        if not image_url:
            return None

        # 2. 미디어 컨테이너 생성
        creation_id = self._create_media_container(image_url, caption)
        if not creation_id:
            return None

        # 3. 처리 완료 대기 (이미지는 보통 즉시 FINISHED)
        if not self._wait_for_media_ready(creation_id):
            return None

        # 4. 게시
        return self._publish_media(creation_id)

    def refresh_token(self) -> str | None:
        """
        토큰을 60일 연장
        반환: 새 액세스 토큰 (갱신 성공 시) 또는 None

        ※ 갱신된 토큰은 GitHub Secret(INSTAGRAM_ACCESS_TOKEN)에 수동 업데이트 필요
        """
        try:
            resp = requests.get(
                "https://graph.instagram.com/refresh_access_token",
                params={
                    "grant_type": "ig_refresh_token",
                    "access_token": self.access_token,
                },
                timeout=15,
            )
            if resp.ok:
                new_token = resp.json().get("access_token")
                if new_token:
                    self.access_token = new_token
                    log.info("Instagram 토큰 갱신 완료 (+60일)")
                    log.info(f"[ACTION REQUIRED] GitHub Secret 'INSTAGRAM_ACCESS_TOKEN' 업데이트: {new_token[:20]}...")
                    return new_token
            log.warning(f"Instagram 토큰 갱신 실패: {resp.text[:200]}")
            return None
        except Exception as e:
            log.warning(f"Instagram 토큰 갱신 오류: {e}")
            return None


def build_caption(concept: dict, youtube_url: str | None = None) -> str:
    """
    concept 데이터로 Instagram 캡션 생성

    구성: 이모지 제목 + 설명 + 유튜브 안내 + 해시태그
    """
    title = concept.get("title", "")
    mood = concept.get("mood", "")
    hours = concept.get("duration_hours", 1)
    tags = concept.get("tags", [])

    # 해시태그 (최대 20개, 공백 제거)
    hashtags = " ".join(
        f"#{t.replace(' ', '').replace('#', '')}"
        for t in tags[:20]
    )
    base_tags = "#힐링음악 #ASMR #수면음악 #백색소음 #자연소리 #relaxation #sleepsounds #calmsounds"

    yt_line = "📺 풀버전은 프로필 링크에서 확인하세요 🔗" if not youtube_url else \
              f"📺 풀버전 YouTube → 프로필 링크\n🔗 {youtube_url}"

    caption = f"""✨ {title}

😴 {hours}시간의 {mood} 사운드스케이프
공부, 업무, 명상, 숙면에 최적화되어 있습니다.
🎧 이어폰으로 들으시면 더욱 좋습니다.

{yt_line}

{hashtags}
{base_tags}"""

    return caption.strip()
