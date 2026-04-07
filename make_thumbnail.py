"""
썸네일 단독 생성 스크립트
사용법:
  python make_thumbnail.py --title "빗소리 ASMR Rain Sounds | 틀어두면 잠드는 소리" \
                           --category rain \
                           --title_sub "잠잘때 듣기 좋은" \
                           --subtitle_en "Cozy Rain Night"

영상 파일은 assets/thumbnail_source/ 폴더에 넣어두면 자동으로 첫 프레임 사용
없으면 그라디언트 배경으로 생성

결과물: output/thumbnails/ 폴더에 저장
"""
import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

SOURCE_DIR = Path("assets/thumbnail_source")
OUTPUT_DIR = Path("output/thumbnails")


def find_source(source_dir: Path) -> tuple[Path | None, str]:
    """thumbnail_source 폴더에서 영상 또는 이미지 파일 찾기
    Returns: (path, type) type은 "video" 또는 "image"
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
    parser.add_argument("--video",       default="",     help="영상 파일 경로 (없으면 thumbnail_source/ 자동 탐색)")
    parser.add_argument("--output",      default="",     help="출력 파일명 (없으면 자동 생성)")
    args = parser.parse_args()

    # 출력 폴더 생성
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 소스 파일 탐색 (이미지 or 영상)
    video_path = None
    image_path = None

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
    else:
        src, src_type = find_source(SOURCE_DIR)
        if src and src_type == "image":
            image_path = src
            log.info(f"이미지 자동 탐색: {src}")
        elif src and src_type == "video":
            video_path = src
            log.info(f"영상 자동 탐색: {src}")
        else:
            log.info(f"소스 없음 → 그라디언트 배경 사용 ({SOURCE_DIR}/ 에 jpg/mp4 넣어주세요)")

    # title_sub, subtitle_en 자동 생성 (없으면 제목에서 추론)
    from planner.concept_generator import CATEGORY_KO
    category_name = CATEGORY_KO.get(args.category, args.category)

    title_sub   = args.title_sub   or category_name[:8]
    subtitle_en = args.subtitle_en or " ".join(
        w.capitalize() for w in args.category.split("_")[:3]
    )

    # 출력 파일명
    import re, random
    safe = re.sub(r'[\\/*?:"<>|]', "_", args.title.split("|")[0].strip())[:30]
    output_name = args.output or f"thumb_{safe}_{random.randint(1000,9999)}.jpg"

    # 썸네일 생성
    from producer.thumbnail import ThumbnailGenerator
    from PIL import Image

    gen = ThumbnailGenerator(OUTPUT_DIR.parent)

    # 이미지 배경인 경우 thumbnail.py의 generate()에 맞게 처리
    if image_path:
        # 이미지를 임시 video_path 대신 직접 배경으로 주입
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

    print(f"\n✅ 썸네일 생성 완료!")
    print(f"   파일: {thumb}")
    print(f"   제목: {args.title.split('|')[0].strip()}")
    print(f"   카테고리: {args.category} ({category_name})")
    print(f"   title_sub: {title_sub}")
    print(f"   subtitle_en: {subtitle_en}")


if __name__ == "__main__":
    main()