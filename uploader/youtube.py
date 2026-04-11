"""
YouTube Data API v3 Uploader
2026.03.29 영상 + 썸네일 자동 업로드
2026.03.29 매일 고정 시각 예약 공개 (기본 오후 8시 KST)
2026.04.11 set_thumbnail()에 제목 변경 기능 추가, youtube 스코프 추가

[사전 준비]
1. Google Cloud Console → YouTube Data API v3 활성화
2. OAuth 2.0 클라이언트 ID 생성 (데스크톱 앱)
3. JSON 다운로드 → credentials/client_secret.json 저장
4. 첫 실행 시 브라우저 인증 → credentials/token.json 자동 생성

[예약 공개 시각]
config.py의 upload_hour_kst (기본 20 = 오후 8시 KST)
"""

import logging
import pickle
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# KST = UTC+9
KST = timezone(timedelta(hours=9))

# YouTube API 스코프
# youtube.upload : 영상 업로드, 썸네일 변경
# youtube        : 제목 등 영상 메타데이터 수정 (videos.update)
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def _get_credentials(client_secret_path: Path, token_path: Path):
    """
    OAuth2 토큰 로드 또는 최초 인증 수행
    - token.json 있으면 재사용 (자동 갱신)
    - 없으면 브라우저 인증 진행
    """
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        raise ImportError(
            "Google API 라이브러리 없음. 설치:\n"
            "pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
        )

    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            log.info("YouTube 토큰 갱신 완료")
        else:
            log.info("YouTube OAuth 인증 시작 — 브라우저가 열립니다")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secret_path), SCOPES
            )
            creds = flow.run_local_server(port=0)
            log.info("YouTube OAuth 인증 완료")

        # 토큰 저장
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        log.info(f"토큰 저장: {token_path}")

    return creds


def _next_publish_time(hour_kst: int, minute_kst: int = 0) -> str:
    """
    다음날 N시 M분 KST를 RFC 3339 형식으로 반환 (항상 익일)
    예: "2026-03-29T18:30:00+09:00"
    """
    now_kst = datetime.now(KST)
    tomorrow = now_kst + timedelta(days=1)
    target = tomorrow.replace(hour=hour_kst, minute=minute_kst, second=0, microsecond=0)

    return target.isoformat()


class YouTubeUploader:

    def __init__(self, client_secret_path: Path, token_path: Path):
        self.client_secret_path = client_secret_path
        self.token_path          = token_path
        self._service            = None

    def _get_service(self):
        if self._service is not None:
            return self._service
        try:
            from googleapiclient.discovery import build
        except ImportError:
            raise ImportError("pip install google-api-python-client")

        creds = _get_credentials(self.client_secret_path, self.token_path)
        self._service = build("youtube", "v3", credentials=creds)
        return self._service

    def upload(
        self,
        video_path:     Path,
        title:          str,
        description:    str,
        tags:           list[str],
        thumbnail_path: Path | None = None,
        category_id:    str = "10",        # 10 = Music
        language:       str = "ko",
        hour_kst:       int = 18,          # 오후 6시 KST
        minute_kst:     int = 30,          # 30분
    ) -> dict | None:
        """
        영상 업로드 + 썸네일 설정 + 예약 공개

        반환: {"video_id": "...", "url": "...", "publish_at": "..."}
        """
        try:
            from googleapiclient.http import MediaFileUpload
        except ImportError:
            raise ImportError("pip install google-api-python-client")

        if not video_path.exists():
            log.error(f"영상 파일 없음: {video_path}")
            return None

        publish_at = _next_publish_time(hour_kst, minute_kst)
        log.info(f"예약 공개 시각: {publish_at}")

        service = self._get_service()

        # ── 영상 메타데이터 ───────────────────────────────────────────
        body = {
            "snippet": {
                "title":                title[:100],     # 최대 100자
                "description":          description[:5000],
                "tags":                 tags[:500],      # 최대 500개
                "categoryId":           category_id,
                "defaultLanguage":      language,
                "defaultAudioLanguage": language,
            },
            "status": {
                "privacyStatus":  "private",    # 예약 공개는 private으로 시작
                "publishAt":      publish_at,   # RFC 3339
                "selfDeclaredMadeForKids": False,
            },
        }

        # ── 업로드 ────────────────────────────────────────────────────
        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True,          # 대용량 파일 재개 가능
            chunksize=10 * 1024 * 1024  # 10MB 청크
        )

        log.info(f"YouTube 업로드 시작: {video_path.name}")
        request = service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                log.info(f"업로드 진행: {pct}%")

        video_id  = response["id"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        log.info(f"업로드 완료: {video_url}")
        log.info(f"예약 공개: {publish_at}")

        # ── 썸네일 설정 ───────────────────────────────────────────────
        if thumbnail_path and thumbnail_path.exists():
            try:
                from googleapiclient.http import MediaFileUpload as MFU
                thumb_media = MFU(str(thumbnail_path), mimetype="image/jpeg")
                service.thumbnails().set(
                    videoId=video_id,
                    media_body=thumb_media
                ).execute()
                log.info(f"썸네일 설정 완료: {thumbnail_path.name}")
            except Exception as e:
                log.warning(f"썸네일 설정 실패 (영상은 업로드됨): {e}")

        return {
            "video_id":   video_id,
            "url":        video_url,
            "publish_at": publish_at,
        }

    def set_thumbnail(
        self,
        video_id:       str,
        thumbnail_path: Path,
        title:          str | None = None,
    ) -> bool:
        """
        이미 업로드된 YouTube 영상의 썸네일 교체 + 제목 변경 (선택)
        영상 재업로드 없이 단독 업데이트

        Args:
            video_id:       YouTube 영상 ID
            thumbnail_path: 썸네일 이미지 경로
            title:          변경할 제목 (None이면 제목 유지)

        반환: 성공 시 True, 실패 시 False
        """
        if not thumbnail_path.exists():
            log.error(f"썸네일 파일 없음: {thumbnail_path}")
            return False

        service = self._get_service()

        try:
            # ── 1. 썸네일 교체 ──────────────────────────────────────────
            from googleapiclient.http import MediaFileUpload
            thumb_media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")
            service.thumbnails().set(
                videoId=video_id,
                media_body=thumb_media
            ).execute()
            log.info(f"썸네일 업데이트 완료: https://www.youtube.com/watch?v={video_id}")
        except Exception as e:
            log.error(f"YouTube 썸네일 업데이트 실패 (video_id={video_id}): {e}")
            return False

        # ── 2. 제목 변경 (title 지정 시) ────────────────────────────────
        if title:
            try:
                # 현재 snippet 조회 (기존 설명/태그 등 보존 필요)
                resp = service.videos().list(
                    part="snippet",
                    id=video_id
                ).execute()

                items = resp.get("items", [])
                if not items:
                    log.error(f"영상을 찾을 수 없음: {video_id}")
                    return False

                snippet = items[0]["snippet"]
                snippet["title"] = title[:100]  # YouTube 제목 최대 100자

                service.videos().update(
                    part="snippet",
                    body={"id": video_id, "snippet": snippet}
                ).execute()
                log.info(f"제목 업데이트 완료: {title[:60]}{'...' if len(title) > 60 else ''}")
            except Exception as e:
                log.error(f"YouTube 제목 업데이트 실패 (video_id={video_id}): {e}")
                return False

        return True