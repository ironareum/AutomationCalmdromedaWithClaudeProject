"""
2026.03.26 Thumbnail Generator
2026.03.28 Pillow로 유튜브 썸네일 자동 생성 (1280x720)
2026.03.28 Calmdromeda 로고 자동 삽입
2026.03.28 한글 타이틀 지원
"""

import logging
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

log = logging.getLogger(__name__)

# 로고 파일 경로
LOGO_PATH = Path(__file__).parent.parent / "assets" / "logo.png"

# 카테고리별 색상 테마
THEMES = {
    "rain": {
        "bg_colors": [(15, 25, 50), (10, 20, 45)],
        "accent": (100, 160, 255),
        "text": (220, 235, 255),
    },
    "rain_thunder": {
        "bg_colors": [(10, 10, 30), (20, 15, 40)],
        "accent": (180, 100, 255),
        "text": (230, 220, 255),
    },
    "ocean": {
        "bg_colors": [(10, 40, 70), (15, 50, 80)],
        "accent": (80, 200, 220),
        "text": (200, 240, 250),
    },
    "forest": {
        "bg_colors": [(15, 40, 20), (10, 35, 15)],
        "accent": (100, 200, 120),
        "text": (210, 240, 215),
    },
    "birds": {
        "bg_colors": [(30, 50, 20), (25, 45, 15)],
        "accent": (180, 220, 100),
        "text": (230, 245, 210),
    },
    "white_noise": {
        "bg_colors": [(20, 20, 30), (25, 25, 35)],
        "accent": (180, 180, 220),
        "text": (230, 230, 245),
    },
    "cafe": {
        "bg_colors": [(40, 25, 15), (50, 30, 10)],
        "accent": (220, 160, 80),
        "text": (245, 230, 200),
    },
    "camping": {
        "bg_colors": [(20, 15, 10), (30, 20, 10)],
        "accent": (240, 140, 60),
        "text": (250, 225, 190),
    },
}

DEFAULT_THEME = {
    "bg_colors": [(15, 20, 35), (20, 25, 45)],
    "accent": (150, 180, 255),
    "text": (220, 230, 255),
}


class ThumbnailGenerator:
    SIZE = (1280, 720)

    def __init__(self, work_dir: Path):
        self.thumb_dir = work_dir / "thumbnails"
        self.thumb_dir.mkdir(parents=True, exist_ok=True)

    def _get_font(self, size: int):
        """한글 지원 폰트 우선 로드"""
        font_candidates = [
            # 한글 지원 폰트 (Windows)
            "C:/Windows/Fonts/malgunbd.ttf",       # 맑은 고딕 Bold
            "C:/Windows/Fonts/NanumGothicBold.ttf", # 나눔고딕 (설치된 경우)
            "C:/Windows/Fonts/gulim.ttc",           # 굴림
            # 영문 폰트 fallback
            "C:/Windows/Fonts/arialbd.ttf",  # Windows
            "/System/Library/Fonts/Helvetica.ttc",  # macOS
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
        ]
        for path in font_candidates:
            try:
                return ImageFont.truetype(path, size)
            except (OSError, IOError):
                continue
        return ImageFont.load_default()

    def _create_gradient_bg(self, colors: list) -> Image.Image:
        """그라디언트 배경 생성"""
        img = Image.new("RGB", self.SIZE)
        draw = ImageDraw.Draw(img)
        w, h = self.SIZE

        c1, c2 = colors[0], colors[1]
        for y in range(h):
            t = y / h
            r = int(c1[0] + (c2[0] - c1[0]) * t)
            g = int(c1[1] + (c2[1] - c1[1]) * t)
            b = int(c1[2] + (c2[2] - c1[2]) * t)
            draw.line([(0, y), (w, y)], fill=(r, g, b))
        return img

    def _add_particles(self, img: Image.Image, color: tuple, count: int = 40):
        """장식용 파티클(원) 추가"""
        draw = ImageDraw.Draw(img, "RGBA")
        w, h = self.SIZE
        for _ in range(count):
            x = random.randint(0, w)
            y = random.randint(0, h)
            radius = random.randint(1, 4)
            alpha = random.randint(30, 100)
            draw.ellipse(
                [(x - radius, y - radius), (x + radius, y + radius)],
                fill=(*color, alpha)
            )
        return img

    def _add_logo(self, img: Image.Image) -> Image.Image:
        """우측 하단에 로고 삽입"""
        if not LOGO_PATH.exists():
            log.warning(f"Logo not found: {LOGO_PATH}")
            return img

        try:
            logo = Image.open(LOGO_PATH).convert("RGBA")

            # 로고 크기: 너비 160px로 리사이즈
            logo_w = 160
            ratio = logo_w / logo.width
            logo_h = int(logo.height * ratio)
            logo = logo.resize((logo_w, logo_h), Image.LANCZOS)

            # 반투명 처리 (80% 불투명)
            r, g, b, a = logo.split()
            a = a.point(lambda x: int(x * 0.8))
            logo.putalpha(a)

            # 우측 하단 배치 (마진 20px)
            w, h = self.SIZE
            pos = (w - logo_w - 20, h - logo_h - 20)

            img_rgba = img.convert("RGBA")
            img_rgba.paste(logo, pos, logo)
            return img_rgba.convert("RGB")
        except Exception as e:
            log.warning(f"Logo insert failed: {e}")
            return img

    def generate(self, title: str, category: str, output_name: str = None) -> Path:
        """
        썸네일 생성 메인 함수
        """
        theme = THEMES.get(category, DEFAULT_THEME)
        w, h = self.SIZE

        # 1. 그라디언트 배경
        img = self._create_gradient_bg(theme["bg_colors"])

        # 2. 파티클 효과
        img = self._add_particles(img, theme["accent"])

        # 2. 중앙 글로우 효과
        glow = Image.new("RGBA", self.SIZE, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        for r in range(200, 0, -20):
            alpha = int(40 * (1 - r / 200))
            gd.ellipse(
                [(w//2 - r*2, h//2 - r), (w//2 + r*2, h//2 + r)],
                fill=(*theme["accent"], alpha)
            )
        img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")

        draw = ImageDraw.Draw(img)

        # 3. 메인 타이틀 (파이프 기준 앞부분만 사용)
        display_title = title.split("|")[0].strip() if "|" in title else title

        # 줄 나누기
        words = display_title.split()
        mid = len(words) // 2
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])

        title_font = self._get_font(58)

        for line, y_pos in [(line1, h // 2 - 60), (line2, h // 2 + 10)]:
            if not line:
                continue
            bbox = draw.textbbox((0, 0), line, font=title_font)
            text_w = bbox[2] - bbox[0]
            x = (w - text_w) // 2
            # 그림자
            draw.text((x + 3, y_pos + 3), line, font=title_font, fill=(0, 0, 0))
            # 본문
            draw.text((x, y_pos), line, font=title_font, fill=theme["text"])

        # 4. 하단 정보 (시간 표시)
        info_font = self._get_font(26)
        if "3시간" in title or "3 Hour" in title.lower():
            duration_text = "3시간" if any(ord(c) > 127 for c in title) else "3 HOURS"
        elif "1시간" in title or "1 Hour" in title.lower():
            duration_text = "1시간" if any(ord(c) > 127 for c in title) else "1 HOUR"
        else:
            duration_text = "LONG VERSION"

        draw.text((40, h - 50), duration_text, font=info_font, fill=theme["accent"])
        draw.text((w - 160, h - 50), "• NO ADS", font=info_font, fill=theme["accent"])

        # 5. 로고 삽입 (우측 하단)
        img = self._add_logo(img)

        # 6. 저장
        fname = output_name or f"thumb_{category}_{random.randint(1000, 9999)}.jpg"
        out_path = self.thumb_dir / fname
        img.save(out_path, "JPEG", quality=95)
        log.info(f"Thumbnail saved: {out_path.name}")
        return out_path
