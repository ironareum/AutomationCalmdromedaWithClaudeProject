"""
Instagram Reels Uploader
2026.04.13 신규: 썸네일 이미지 게시 (YouTube 영상 홍보)
2026.04.13 fix:  이미지 게시 → Reels 영상 업로드로 전환 (Meta 자체 resumable upload API 사용)

[업로드 흐름]
1. POST /{user-id}/media  (upload_type=resumable)  → container_id + upload_uri 획득
2. POST {upload_uri}       (영상 바이너리 전송)
3. GET  /{container_id}   → status_code 폴링 (IN_PROGRESS → FINISHED)
4. POST /{user-id}/media_publish (creation_id=container_id) → 게시

[사전 준비]
1. Meta Developer Console → Calmdromeda 앱 → Instagram 제품 설정
2. Graph API Explorer → Instagram 장기 액세스 토큰 발급 (60일)
3. .env / GitHub Secrets에 아래 항목 설정:
   - INSTAGRAM_ACCESS_TOKEN
   - INSTAGRAM_USER_ID  (예: 27312581898330133)

[토큰 갱신]
- 장기 토큰은 60일 유효
- 파이프라인 실행 시 자동으로 갱신 시도 (ig_refresh_token 호출)
- 갱신된 토큰은 로그에 출력 → GitHub Secret 수동 업데이트 필요
"""

import logging
import time
import requests
from pathlib import Path

log = logging.getLogger(__name__)

GRAPH_URL = "https://graph.instagram.com/v25.0"


class InstagramUploader:

    def __init__(self, access_token: str, user_id: str):
        self.access_token = access_token
        self.user_id = user_id

    # ── Step 1: Resumable 업로드 세션 초기화 ─────────────────────────────

    def _init_resumable_upload(self, video_path: Path, caption: str) -> tuple[str, str] | None:
        """
        Meta에 Reel 컨테이너 + 업로드 URI 요청
        반환: (container_id, upload_uri) 또는 None
        """
        file_size = video_path.stat().st_size
        try:
            resp = requests.post(
                f"{GRAPH_URL}/{self.user_id}/media",
                data={
                    "media_type":   "REELS",
                    "upload_type":  "resumable",
                    "caption":      caption,
                    "share_to_feed": "true",
                    "access_token": self.access_token,
                },
                timeout=30,
            )
            if not resp.ok:
                log.error(f"Reel 컨테이너 초기화 실패: {resp.status_code} | {resp.text}")
                return None
            data = resp.json()
            container_id = data.get("id")
            upload_uri   = data.get("uri")
            if not container_id or not upload_uri:
                log.error(f"Reel 컨테이너 응답 이상: {data}")
                return None
            log.info(f"Reel 컨테이너 생성: {container_id} | 파일 크기: {file_size // 1024}KB")
            return container_id, upload_uri
        except Exception as e:
            log.error(f"Reel 컨테이너 초기화 오류: {e}")
            return None

    # ── Step 2: 영상 바이너리 업로드 ─────────────────────────────────────

    def _upload_video_file(self, upload_uri: str, video_path: Path) -> bool:
        """
        영상 파일을 Meta 업로드 URI에 직접 전송
        """
        file_size = video_path.stat().st_size
        try:
            with open(video_path, "rb") as f:
                resp = requests.post(
                    upload_uri,
                    headers={
                        "Authorization":  f"OAuth {self.access_token}",
                        "offset":         "0",
                        "file_size":      str(file_size),
                        "Content-Type":   "application/octet-stream",
                    },
                    data=f,
                    timeout=300,  # 영상 업로드는 최대 5분
                )
            if not resp.ok:
                log.error(f"영상 업로드 실패: {resp.status_code} | {resp.text}")
                return False
            result = resp.json()
            if not result.get("success"):
                log.error(f"영상 업로드 응답 이상: {result}")
                return False
            log.info(f"영상 업로드 완료: {video_path.name} ({file_size // 1024}KB)")
            return True
        except Exception as e:
            log.error(f"영상 업로드 오류: {e}")
            return False

    # ── Step 3: 처리 완료 대기 ────────────────────────────────────────────

    def _wait_for_media_ready(self, container_id: str, max_wait: int = 300) -> bool:
        """
        Meta 서버의 영상 처리 완료 대기 (최대 max_wait초, 10초 간격)
        Reels는 이미지보다 처리 시간이 길어 기본값 300초
        """
        for attempt in range(max_wait // 10):
            try:
                resp = requests.get(
                    f"{GRAPH_URL}/{container_id}",
                    params={"fields": "status_code", "access_token": self.access_token},
                    timeout=15,
                )
                status = resp.json().get("status_code", "")
                log.info(f"Reel 처리 상태: {status} (시도 {attempt + 1})")
                if status == "FINISHED":
                    return True
                if status == "ERROR":
                    log.error(f"Reel 처리 오류: {resp.json()}")
                    return False
                time.sleep(10)
            except Exception as e:
                log.warning(f"상태 확인 중 오류: {e}")
                time.sleep(10)
        log.error(f"Reel 처리 타임아웃 ({max_wait}초 초과)")
        return False

    # ── Step 4: 게시 ──────────────────────────────────────────────────────

    def _publish_media(self, container_id: str) -> dict | None:
        """Reel 게시"""
        try:
            resp = requests.post(
                f"{GRAPH_URL}/{self.user_id}/media_publish",
                data={
                    "creation_id":  container_id,
                    "access_token": self.access_token,
                },
                timeout=30,
            )
            if not resp.ok:
                log.error(f"Reel 게시 실패: {resp.status_code} | {resp.text}")
                return None
            post_id = resp.json()["id"]
            log.info(f"Instagram Reel 게시 완료: post_id={post_id}")
            return {"post_id": post_id}
        except Exception as e:
            log.error(f"Reel 게시 오류: {e}")
            return None

    # ── 공개 인터페이스 ──────────────────────────────────────────────────

    def post_reel(self, video_path: Path, caption: str) -> dict | None:
        """
        Shorts 영상 파일을 Instagram Reel로 업로드

        Args:
            video_path: Shorts 영상 파일 경로 (.mp4)
            caption:    게시물 캡션 (해시태그 포함)

        반환: {"post_id": "..."} 또는 None (실패 시)
        """
        if not video_path or not video_path.exists():
            log.error(f"영상 파일 없음: {video_path}")
            return None

        log.info(f"Instagram Reels 업로드 시작: {video_path.name}")

        # 1. Reel 컨테이너 + 업로드 URI 초기화
        result = self._init_resumable_upload(video_path, caption)
        if not result:
            return None
        container_id, upload_uri = result

        # 2. 영상 바이너리 Meta 서버에 전송
        if not self._upload_video_file(upload_uri, video_path):
            return None

        # 3. 처리 완료 대기
        if not self._wait_for_media_ready(container_id):
            return None

        # 4. 게시
        return self._publish_media(container_id)

    # ── 토큰 관리 ────────────────────────────────────────────────────────

    def refresh_token(self) -> str | None:
        """
        토큰을 60일 연장
        반환: 새 액세스 토큰 또는 None

        ※ 갱신된 토큰은 GitHub Secret(INSTAGRAM_ACCESS_TOKEN)에 수동 업데이트 필요
        """
        try:
            resp = requests.get(
                "https://graph.instagram.com/refresh_access_token",
                params={
                    "grant_type":   "ig_refresh_token",
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
    title  = concept.get("title", "")
    mood   = concept.get("mood", "")
    hours  = concept.get("duration_hours", 1)
    tags   = concept.get("tags", [])

    hashtags  = " ".join(
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
