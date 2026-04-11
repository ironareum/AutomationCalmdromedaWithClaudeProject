"""
썸네일 단독 생성 스크립트
사용법:
  # 세션 ID로 Pexels 소스 자동 재다운로드 + YouTube 썸네일 업데이트
  python make_thumbnail.py --title "빗소리 ASMR | 창밖에 비 올 때 틀어두는 소리 | Rain Sounds - Sleep Music Relaxation" \
                           --category rain \
                           --title_sub "빗소리 힐링" \
                           --subtitle_en "Cozy Rain Night" \
                           --session 20260401_202159 \
                           --video-id "dQw4w9WgXcQ"

  # 영상/이미지 파일 직접 지정 + YouTube 썸네일 업데이트
  python make_thumbnail.py --title "빗소리 ASMR | 창밖에 비 올 때 틀어두는 소리 | Rain Sounds - Sleep Music Relaxation" \
                           --category rain \
                           --title_sub "빗소리 힐링" \
                           --subtitle_en "Cozy Rain Night" \
                           --video path/to/video.mp4 \
                           --video-id "dQw4w9WgXcQ"

  # --video-id 생략 시 썸네일 파일만 생성 (YouTube 업데이트 안 함)

소스 탐색 우선순위:
  1. --video 직접 지정
  2. --session SESSION_ID → used_assets에서 Pexels ID 추출 → API 재다운로드 → 썸네일 생성 후 삭제
  3. assets/thumbnail_source/ 폴더 탐색 (이미지/영상)
  4. 소스 없으면 에러 종료 (그라디언트 배경 미지원)

결과물: output/thumbnails/ 폴더에 저장
"""
import argparse
import json
import logging
import re
import sys
import tempfile
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

SOURCE_DIR = Path("assets/thumbnail_source")
OUTPUT_DIR = Path("output/thumbnails")
USED_ASSETS_JSON     = Path("used_assets.json")
USED_ASSETS_JSON_ENC = Path("used_assets.json.enc")


# ── used_assets 로드 (plain → enc 폴백) ──────────────────────────────
def _load_used_assets() -> dict:
    if USED_ASSETS_JSON.exists():
        return json.loads(USED_ASSETS_JSON.read_text(encoding="utf-8"))
    if USED_ASSETS_JSON_ENC.exists():
        from crypto_utils import decrypt_to_str
        log.info("used_assets.json.enc 복호화 중...")
        return json.loads(decrypt_to_str(USED_ASSETS_JSON_ENC))
    raise FileNotFoundError(
        "used_assets.json / used_assets.json.enc 를 찾을 수 없습니다.\n"
        "data 브랜치에서 used_assets.json.enc 를 가져오거나 --video 로 직접 지정하세요."
    )


# ── Pexels 파일명에서 video ID 추출 ──────────────────────────────────
def _extract_pexels_id(filename: str) -> str | None:
    """
    파일명 형식: pexels_{video_id}_{height}p.mp4
    예: pexels_12345678_1080p.mp4 → "12345678"
    """
    m = re.match(r"pexels_(\d+)_", filename)
    return m.group(1) if m else None


# ── thumbnail_source 폴더 탐색 ───────────────────────────────────────
def _find_source(source_dir: Path) -> tuple[Path | None, str]:
    """
    Returns: (path, type) type은 "video" 또는 "image"
    이미지 우선 → 영상 순
    """
    if not source_dir.exists():
        return None, ""
    for ext in ["*.jpg", "*.jpeg", "*.png"]:
        files = list(source_dir.glob(ext))
        if files:
            return files[0], "image"
    for ext in ["*.mp4", "*.mov", "*.avi", "*.mkv"]:
        files = list(source_dir.glob(ext))
        if files:
            return files[0], "video"
    return None, ""


def main():
    parser = argparse.ArgumentParser(description="Calmdromeda 썸네일 단독 생성")
    parser.add_argument("--title",       required=True,  help="영상 제목 (| 구분 형식)")
    parser.add_argument("--category",    default="forest", help="카테고리 (테마 색상 결정)")
    parser.add_argument("--title_sub",   default="",     help="썸네일 상단 짧은 문구 (10자 이내)")
    parser.add_argument("--subtitle_en", default="",     help="썸네일 하단 영문 (2~4단어)")
    parser.add_argument("--video",       default="",     help="영상/이미지 파일 직접 지정")
    parser.add_argument("--session",     default="",     help="세션 ID (used_assets에서 Pexels 소스 자동 탐색)")
    parser.add_argument("--video-id",    default="",     dest="youtube_video_id",
                        help="YouTube 영상 ID (지정 시 썸네일 자동 업데이트)")
    parser.add_argument("--output",      default="",     help="출력 파일명 (없으면 자동 생성)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── title_sub / subtitle_en 자동 추론 ────────────────────────────
    from planner.concept_generator import CATEGORY_KO
    category_name = CATEGORY_KO.get(args.category, args.category)
    title_sub   = args.title_sub   or category_name[:8]
    subtitle_en = args.subtitle_en or " ".join(
        w.capitalize() for w in args.category.split("_")[:3]
    )

    # ── 출력 파일명 ──────────────────────────────────────────────────
    import random
    safe = re.sub(r'[\\/*?:"<>|]', "_", args.title.split("|")[0].strip())[:30]
    output_name = args.output or f"thumb_{safe}_{random.randint(1000,9999)}.jpg"

    # ════════════════════════════════════════════════════════════════
    # 소스 탐색 (우선순위 순)
    # ════════════════════════════════════════════════════════════════
    video_path = None
    image_path = None
    _pexels_tmp_dir = None   # 임시 다운로드 폴더 (--session 사용 시)

    # ── 1. --video 직접 지정 ─────────────────────────────────────────
    if args.video:
        src = Path(args.video)
        if not src.exists():
            log.error(f"파일 없음: {src}")
            sys.exit(1)
        if src.suffix.lower() in [".jpg", ".jpeg", ".png"]:
            image_path = src
            log.info(f"이미지 배경 사용: {src}")
        else:
            video_path = src
            log.info(f"영상 배경 사용: {src}")

    # ── 2. --session → used_assets에서 Pexels ID 추출 후 재다운로드 ──
    elif args.session:
        session_id = args.session
        log.info(f"세션 소스 탐색: {session_id}")

        try:
            used = _load_used_assets()
        except FileNotFoundError as e:
            log.error(str(e))
            sys.exit(1)

        if session_id not in used:
            log.error(f"세션을 찾을 수 없습니다: {session_id}")
            log.error(f"등록된 세션 목록: {list(used.keys())[-5:]}")
            sys.exit(1)

        session_data = used[session_id]
        videos = session_data.get("videos", [])
        if not videos:
            log.error(f"세션 {session_id}에 영상 기록이 없습니다.")
            sys.exit(1)

        first_video_name = videos[0]
        pexels_id = _extract_pexels_id(first_video_name)

        if not pexels_id:
            log.warning(f"Pexels 파일명 형식이 아닙니다: {first_video_name}")
            log.info("→ assets/thumbnail_source/ 탐색으로 넘어갑니다.")
        else:
            log.info(f"Pexels video ID 추출: {pexels_id} (from {first_video_name})")
            from config import Config
            from collector.pexels import PexelsCollector

            cfg = Config()
            _pexels_tmp_dir = Path(tempfile.mkdtemp(prefix="thumb_pexels_"))

            collector = PexelsCollector(cfg.pexels_api_key, _pexels_tmp_dir)
            video_info = collector.fetch_by_id(pexels_id)

            if not video_info:
                log.error(f"Pexels에서 영상 조회 실패 (id={pexels_id})")
                sys.exit(1)

            downloaded = collector.download(video_info, filename=first_video_name)
            if not downloaded:
                log.error(f"Pexels 영상 다운로드 실패 (id={pexels_id})")
                sys.exit(1)

            video_path = downloaded
            log.info(f"Pexels 영상 임시 다운로드 완료: {video_path}")

    # ── 3. assets/thumbnail_source/ 탐색 ────────────────────────────
    if video_path is None and image_path is None:
        src, src_type = _find_source(SOURCE_DIR)
        if src_type == "image":
            image_path = src
            log.info(f"이미지 자동 탐색: {src}")
        elif src_type == "video":
            video_path = src
            log.info(f"영상 자동 탐색: {src}")
        else:
            log.error(
                "소스를 찾을 수 없습니다.\n"
                "  --video 로 파일을 직접 지정하거나,\n"
                "  --session 으로 세션 ID를 지정하거나,\n"
                f"  {SOURCE_DIR}/ 폴더에 jpg/png/mp4 파일을 넣어주세요."
            )
            sys.exit(1)

    # ════════════════════════════════════════════════════════════════
    # 썸네일 생성
    # ════════════════════════════════════════════════════════════════
    from producer.thumbnail import ThumbnailGenerator

    gen = ThumbnailGenerator(OUTPUT_DIR.parent)

    try:
        if image_path:
            thumb = gen.generate_from_image(
                title       = args.title,
                category    = args.category,
                image_path  = image_path,
                title_sub   = title_sub,
                subtitle_en = subtitle_en,
                output_name = output_name,
            )
        else:
            thumb = gen.generate(
                title       = args.title,
                category    = args.category,
                video_path  = video_path,
                title_sub   = title_sub,
                subtitle_en = subtitle_en,
                output_name = output_name,
            )
    finally:
        # --session으로 임시 다운로드한 영상 삭제
        if _pexels_tmp_dir and _pexels_tmp_dir.exists():
            import shutil
            shutil.rmtree(_pexels_tmp_dir, ignore_errors=True)
            log.info("임시 Pexels 영상 삭제 완료")

    print(f"\n썸네일 생성 완료!")
    print(f"   파일     : {thumb}")
    print(f"   제목     : {args.title.split('|')[0].strip()}")
    print(f"   카테고리 : {args.category} ({category_name})")
    print(f"   title_sub: {title_sub}")
    print(f"   subtitle : {subtitle_en}")

    # ════════════════════════════════════════════════════════════════
    # YouTube 썸네일 업데이트 (--video-id 지정 시)
    # ════════════════════════════════════════════════════════════════
    if args.youtube_video_id:
        from config import Config
        from uploader.youtube import YouTubeUploader

        cfg = Config()
        log.info(f"YouTube 썸네일 업데이트 시작: {args.youtube_video_id}")

        uploader = YouTubeUploader(
            client_secret_path = Path(cfg.youtube_client_secret_path),
            token_path         = Path(cfg.youtube_token_path),
        )
        success = uploader.set_thumbnail(args.youtube_video_id, thumb)

        if success:
            print(f"   YouTube  : 썸네일 업데이트 완료 → https://www.youtube.com/watch?v={args.youtube_video_id}")
        else:
            print(f"   YouTube  : 썸네일 업데이트 실패 (로그 확인)")
            sys.exit(1)


if __name__ == "__main__":
    main()
