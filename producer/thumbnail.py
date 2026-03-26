"""
Thumbnail Generator
Pillow로 유튜브 썸네일 자동 생성 (1280x720)
"""

import logging
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

log = logging.getLogger(__name__)

# 카테고리별 색상 테마
THEMES = {
    "rain": {
        "bg_colors": [(15, 25, 50), (10, 20, 45)],
        "accent": (100, 160, 255),
        "text": (220, 235, 255),
        "emoji": "🌧️",
        "overlay_opacity": 160,
    },
    "rain_thunder": {
        "bg_colors": [(10, 10, 30), (20, 15, 40)],
        "accent": (180, 100, 255),
        "text": (230, 220, 255),
        "emoji": "⛈️",
        "overlay_opacity": 170,
    },
    "ocean": {
        "bg_colors": [(10, 40, 70), (15, 50, 80)],
        "accent": (80, 200, 220),
        "text": (200, 240, 250),
        "emoji": "🌊",
        "overlay_opacity": 150,
    },
    "forest": {
        "bg_colors": [(15, 40, 20), (10, 35, 15)],
        "accent": (100, 200, 120),
        "text": (210, 240, 215),
        "emoji": "🌲",
        "overlay_opacity": 155,
    },
    "birds": {
        "bg_colors": [(30, 50, 20), (25, 45, 15)],
        "accent": (180, 220, 100),
        "text": (230, 245, 210),
        "emoji": "🐦",
        "overlay_opacity": 140,
    },
    "white_noise": {
        "bg_colors": [(20, 20, 30), (25, 25, 35)],
        "accent": (180, 180, 220),
        "text": (230, 230, 245),
        "emoji": "〰️",
        "overlay_opacity": 160,
    },
    "cafe": {
        "bg_colors": [(40, 25, 15), (50, 30, 10)],
        "accent": (220, 160, 80),
        "text": (245, 230, 200),
        "emoji": "☕",
        "overlay_opacity": 150,
    },
    "camping": {
        "bg_colors": [(20, 15, 10), (30, 20, 10)],
        "accent": (240, 140, 60),
        "text": (250, 225, 190),
        "emoji": "🔥",
        "overlay_opacity": 155,
    },
}

DEFAULT_THEME = {
    "bg_colors": [(15, 20, 35), (20, 25, 45)],
    "accent": (150, 180, 255),
    "text": (220, 230, 255),
    "emoji": "✨",
    "overlay_opacity": 160,
}


class ThumbnailGenerator:
    SIZE = (1280, 720)

    def __init__(self, work_dir: Path):
        self.thumb_dir = work_dir / "thumbnails"
        self.thumb_dir.mkdir(parents=True, exist_ok=True)

    def _get_font(self, size: int):
        """시스템 폰트 로드 (없으면 기본 폰트)"""
        font_candidates = [
            "/System/Library/Fonts/Supplemental/Futura.ttc",         # macOS
            "/System/Library/Fonts/Helvetica.ttc",                    # macOS
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",  # Linux
            "/Windows/Fonts/arialbd.ttf",                             # Windows
        ]
        for path in font_candidates:
            try:
                return ImageFont.truetype(path, size)
            except (OSError, IOError):
                continue
        return ImageFont.load_default()

    def _create_gradient_bg(self, colors: list[tuple]) -> Image.Image:
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

        # 3. 중앙 글로우 효과
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

        # 4. 채널 브랜드 (상단 좌측)
        brand_font = self._get_font(22)
        draw.text((40, 35), "calmdromeda", font=brand_font, fill=(*theme["accent"], 200) if len(theme["accent"]) == 3 else theme["accent"])

        # 5. 메인 타이틀 — 2줄로 나눔
        words = title.split("|")[0].strip() if "|" in title else title
        # 적당히 줄 나누기
        mid = len(words) // 2
        # 공백 기준으로 가장 가까운 곳에서 분리
        space_positions = [i for i, c in enumerate(words) if c == " "]
        split_pos = min(space_positions, key=lambda x: abs(x - mid)) if space_positions else mid
        line1 = words[:split_pos].strip()
        line2 = words[split_pos:].strip()

        title_font = self._get_font(62)
        shadow_offset = 3

        for line, y_pos in [(line1, h//2 - 55), (line2, h//2 + 15)]:
            if not line:
                continue
            bbox = draw.textbbox((0, 0), line, font=title_font)
            text_w = bbox[2] - bbox[0]
            x = (w - text_w) // 2

            # 그림자
            draw.text((x + shadow_offset, y_pos + shadow_offset), line,
                     font=title_font, fill=(0, 0, 0, 120))
            # 메인 텍스트
            draw.text((x, y_pos), line, font=title_font, fill=theme["text"])

        # 6. 하단 정보 (시간 표시)
        if "3 Hour" in title or "3 hour" in title:
            duration_text = "3 HOURS"
        elif "1 Hour" in title or "1 hour" in title:
            duration_text = "1 HOUR"
        else:
            duration_text = "LONG VERSION"

        info_font = self._get_font(28)
        draw.text((40, h - 55), duration_text, font=info_font, fill=theme["accent"])

        # No Ads 뱃지 (우측 하단)
        draw.text((w - 150, h - 55), "• NO ADS", font=info_font, fill=(*theme["accent"][:3],))

        # 7. 저장
        fname = output_name or f"thumb_{category}_{random.randint(1000,9999)}.jpg"
        out_path = self.thumb_dir / fname
        img.save(out_path, "JPEG", quality=95)
        log.info(f"Thumbnail saved: {out_path.name}")
        return out_path
