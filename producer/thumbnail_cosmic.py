"""
Cosmic Pipeline Thumbnail Generator
2026.06.29 자연소리 파이프라인(thumbnail.py)으로부터 분리

레이아웃 (1280×720):
  상단: [1 HOUR 배지 - 좌상단]    [CALMDROMEDA 헤딩 로고 - 우상단]
  중앙: seo_ko 대형 한글 (카테고리 컬러)
  중하: seo_en 영문 서브
  하단: [  1 Hour Ambient Sound  ] 필 배지
  우하: CALMDROMEDA 원형 로고 (소형)

[설계 원칙]
  - producer/thumbnail.py (자연소리 파이프라인) 수정 금지
  - 필요한 유틸 함수는 이 파일에 독립적으로 정의 (일부 중복 허용)
"""

import logging
import random
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

_BASE        = Path(__file__).parent.parent
LOGO_HEADING = _BASE / "assets" / "logo_heading.png"
LOGO_CIRCLE  = _BASE / "assets" / "logo.png"
FONTS_DIR    = _BASE / "assets" / "fonts"


# ── 폰트 유틸 ──────────────────────────────────────────────────────────────

def _resolve(filename: str) -> str:
    for p in [FONTS_DIR / filename, Path("/mnt/user-data/uploads") / filename]:
        if p.exists():
            return str(p)
    raise FileNotFoundError(f"폰트 없음: {filename} — assets/fonts/ 에 넣어주세요")


def _fnanum(size, weight="extrabold"):
    return ImageFont.truetype(_resolve({
        "regular":   "NanumMyeongjo.ttf",
        "bold":      "NanumMyeongjoBold.ttf",
        "extrabold": "NanumMyeongjoExtraBold.ttf",
    }[weight]), size)


def _fpretendard(size, weight="black"):
    return ImageFont.truetype(_resolve({
        "regular":   "Pretendard-Regular.ttf",
        "medium":    "Pretendard-Medium.ttf",
        "semibold":  "Pretendard-SemiBold.ttf",
        "bold":      "Pretendard-Bold.ttf",
        "extrabold": "Pretendard-ExtraBold.ttf",
        "black":     "Pretendard-Black.ttf",
    }[weight]), size)


def _load_ko_font(size: int):
    """한글 메인 텍스트용: NanumMyeongjoExtraBold → Bold → RIDIBatang"""
    for fn in [
        lambda s: _fnanum(s, "extrabold"),
        lambda s: _fnanum(s, "bold"),
        lambda s: ImageFont.truetype(_resolve("RIDIBatang.otf"), s),
    ]:
        try:
            return fn(size)
        except FileNotFoundError:
            continue
    raise RuntimeError("사용 가능한 한글 폰트 없음")


def _load_en_font(size: int):
    """영문 텍스트용: Pretendard Black → NanumMyeongjoExtraBold → RIDIBatang"""
    for fn in [
        lambda s: _fpretendard(s, "black"),
        lambda s: _fnanum(s, "extrabold"),
        lambda s: ImageFont.truetype(_resolve("RIDIBatang.otf"), s),
    ]:
        try:
            return fn(size)
        except FileNotFoundError:
            continue
    raise RuntimeError("사용 가능한 영문 폰트 없음")


# ── 이미지 유틸 ────────────────────────────────────────────────────────────

def _rm_black(img: Image.Image, thr: int = 45) -> Image.Image:
    img = img.convert("RGBA")
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            if r < thr and g < thr and b < thr:
                px[x, y] = (r, g, b, 0)
    return img


def _hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _stroke_color(img: Image.Image) -> tuple:
    W, H = img.size
    crop = img.crop((W // 4, H // 4, W * 3 // 4, H * 3 // 4))
    small = crop.resize((16, 16), Image.LANCZOS).convert("RGB")
    px = list(small.getdata())
    r = sum(p[0] for p in px) // len(px)
    g = sum(p[1] for p in px) // len(px)
    b = sum(p[2] for p in px) // len(px)
    return tuple(min(int(c * 0.22), 55) for c in (r, g, b))


def _fit_font_size(text: str, max_px: int, max_size: int = 120, min_size: int = 40,
                   font_fn=None) -> int:
    if font_fn is None:
        font_fn = _load_ko_font
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for size in range(max_size, min_size - 1, -2):
        try:
            fnt = font_fn(size)
            bbox = dummy.textbbox((0, 0), text, font=fnt)
            if (bbox[2] - bbox[0]) <= max_px:
                return size
        except Exception:
            pass
    return min_size


def _split_two_lines(text: str):
    text = text.strip()
    spaces = [i for i, c in enumerate(text) if c == " "]
    if not spaces:
        return text, ""
    mid = len(text) // 2
    sp = min(spaces, key=lambda x: abs(x - mid))
    return text[:sp].strip(), text[sp:].strip()


def _stroke_center(draw, text, y, fnt, W,
                   fill=(255, 255, 255), sc=(20, 20, 20), sw=5):
    bbox = draw.textbbox((0, 0), text, font=fnt)
    x = (W - (bbox[2] - bbox[0])) // 2
    for dx in range(-sw, sw + 1):
        for dy in range(-sw, sw + 1):
            if dx == 0 and dy == 0:
                continue
            if abs(dx) + abs(dy) > sw + 2:
                continue
            draw.text((x + dx, y + dy), text, font=fnt, fill=(*sc, 225))
    draw.text((x, y), text, font=fnt, fill=fill)


def _extract_frame(video: Path, out: Path, sec: int = 3) -> bool:
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-ss", str(sec), "-i", str(video),
             "-vframes", "1", "-q:v", "2", str(out)],
            capture_output=True, encoding="utf-8", errors="replace", timeout=30,
        )
        return out.exists() and out.stat().st_size > 0
    except Exception as e:
        log.warning(f"프레임 추출 실패: {e}")
        return False


# ── 로고 ───────────────────────────────────────────────────────────────────

def _paste_logo_tr(base: Image.Image) -> Image.Image:
    """우상단 Heading 로고 (Cosmic 전용 배치)"""
    if not LOGO_HEADING.exists():
        return base
    W, H = base.size
    logo = _rm_black(Image.open(LOGO_HEADING))
    tw = int(W * 0.17)
    th = int(logo.height * tw / logo.width)
    logo = logo.resize((tw, th), Image.LANCZOS)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.paste(logo, (W - tw - 8, 8), logo)
    return Image.alpha_composite(base.convert("RGBA"), layer)


def _paste_logo_br(base: Image.Image) -> Image.Image:
    """우하단 원형 로고 (소형)"""
    if not LOGO_CIRCLE.exists():
        return base
    W, H = base.size
    logo = _rm_black(Image.open(LOGO_CIRCLE))
    sz = 60
    logo = logo.resize((sz, sz), Image.LANCZOS)
    r, g, b, a = logo.split()
    logo.putalpha(a.point(lambda v: int(v * 0.55)))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.paste(logo, (W - sz - 12, H - sz - 12), logo)
    return Image.alpha_composite(base.convert("RGBA"), layer)


# ── 1 HOUR 배지 ────────────────────────────────────────────────────────────

def _draw_hour_badge(draw: ImageDraw.ImageDraw, x: int, y: int, cat_rgb: tuple):
    """좌상단 '1 HOUR' 원형 배지 (지름 84px)"""
    radius = 42
    cx, cy = x + radius, y + radius
    draw.ellipse(
        [(cx - radius, cy - radius), (cx + radius, cy + radius)],
        fill=(*cat_rgb, 160),
        outline=(255, 255, 255, 100),
        width=2,
    )
    try:
        f_num = _load_en_font(30)
        f_hr  = _load_en_font(16)
    except Exception:
        return
    bbox_n = draw.textbbox((0, 0), "1", font=f_num)
    nw = bbox_n[2] - bbox_n[0]
    draw.text((cx - nw // 2, cy - 26), "1", font=f_num, fill=(255, 255, 255, 255))
    bbox_h = draw.textbbox((0, 0), "HOUR", font=f_hr)
    hw = bbox_h[2] - bbox_h[0]
    draw.text((cx - hw // 2, cy + 6), "HOUR", font=f_hr, fill=(255, 255, 255, 210))


# ── 필 배지 ────────────────────────────────────────────────────────────────

def _draw_pill_badge(draw: ImageDraw.ImageDraw, text: str, cx: int, y: int,
                     cat_rgb: tuple, font):
    """가로 중앙 정렬 rounded-rect 배지"""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad_x, pad_y = 28, 10
    rw = tw + pad_x * 2
    rh = th + pad_y * 2
    x0 = cx - rw // 2
    y0 = y
    x1 = x0 + rw
    y1 = y0 + rh
    try:
        draw.rounded_rectangle(
            [(x0, y0), (x1, y1)],
            radius=rh // 2,
            fill=(*cat_rgb, 35),
            outline=(*cat_rgb, 120),
            width=1,
        )
    except TypeError:
        # Pillow < 9.2: outline without width
        draw.rounded_rectangle([(x0, y0), (x1, y1)], radius=rh // 2,
                               fill=(*cat_rgb, 35), outline=(*cat_rgb, 120))
    draw.text((x0 + pad_x, y0 + pad_y - bbox[1]), text, font=font,
              fill=(225, 225, 225, 255))


# ── Thumbnail Generator ────────────────────────────────────────────────────

class CosmicThumbnailGenerator:
    """코스믹 파이프라인 전용 썸네일 생성기 (ThumbnailGenerator 와 독립)."""

    SIZE = (1280, 720)

    def __init__(self, work_dir: Path):
        self.thumb_dir = work_dir / "thumbnails"
        self.thumb_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        video_path:     Path | None = None,
        seo_ko:         str = "",
        seo_en:         str = "",
        category_color: str = "#5B7FFF",
        series_number:  int | None = None,
        output_name:    str | None = None,
    ) -> Path:
        """
        영상 첫 프레임을 배경으로 코스믹 썸네일 생성.
        프레임 추출 실패 시 다크 그라디언트 폴백.
        """
        bg = None
        if video_path and video_path.exists():
            frame_jpg = self.thumb_dir / f"_frame_{video_path.stem}.jpg"
            if _extract_frame(video_path, frame_jpg):
                try:
                    bg = Image.open(frame_jpg).convert("RGB")
                    log.info(f"썸네일 배경: {video_path.name} 첫 프레임")
                except Exception as e:
                    log.warning(f"프레임 로드 실패: {e}")
        if not bg:
            log.info("썸네일 배경: 다크 그라디언트 폴백")

        return self._render(bg, seo_ko, seo_en, category_color, series_number, output_name)

    def _render(
        self,
        bg:             Image.Image | None,
        seo_ko:         str,
        seo_en:         str,
        category_color: str,
        series_number:  int | None,
        output_name:    str | None,
    ) -> Path:
        W, H = self.SIZE
        cat_rgb = _hex_to_rgb(category_color)
        sc = _stroke_color(bg) if bg else (5, 5, 20)

        # ── 1. 배경 ────────────────────────────────────────────────────
        if bg:
            base = bg.resize((W, H), Image.LANCZOS).convert("RGBA")
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            od = ImageDraw.Draw(ov)
            for yi in range(H):
                a = int(155 * 0.6 + 155 * 0.4 * yi / H)
                od.line([(0, yi), (W, yi)], fill=(0, 0, 0, a))
            base = Image.alpha_composite(base, ov)
        else:
            base = Image.new("RGBA", (W, H), (8, 17, 31, 255))

        # ── 2. 카테고리 컬러 글로우 ────────────────────────────────────
        gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gl)
        gx, gy = W // 2, H // 2 + 20
        for r in range(320, 0, -32):
            a = int(9 * (1 - r / 320))
            gd.ellipse([(gx - r * 2, gy - r), (gx + r * 2, gy + r)], fill=(*cat_rgb, a))
        base = Image.alpha_composite(base.convert("RGBA"), gl)
        draw = ImageDraw.Draw(base)

        # ── 3. 한글 메인 텍스트 폰트 크기 계산 ────────────────────────
        max_w = int(W * 0.78)
        l1, l2 = _split_two_lines(seo_ko)
        longer = l1 if len(l1) >= len(l2) else l2
        ko_size = _fit_font_size(longer, max_w, max_size=130, min_size=50, font_fn=_load_ko_font)
        f_ko = _load_ko_font(ko_size)
        ko_line_h = int(ko_size * 1.25)
        ko_total_h = ko_line_h * (2 if l2 else 1)

        # ── 4. 보조 텍스트 폰트 ────────────────────────────────────────
        f_en_sub = _load_en_font(30)
        f_pill   = _load_en_font(22)

        # 시리즈 번호 표시 (옵션)
        series_h = 36 if series_number is not None else 0
        f_series = _load_en_font(22) if series_number is not None else None

        en_sub_h    = 42
        pill_h      = 46
        gap_ko_en   = 18
        gap_en_pill = 14

        total_h = series_h + ko_total_h + gap_ko_en + en_sub_h + gap_en_pill + pill_h
        y_start = (H - total_h) // 2 - 5

        y_series = y_start
        y_ko     = y_start + series_h
        y_en     = y_ko + ko_total_h + gap_ko_en
        y_pill   = y_en + en_sub_h + gap_en_pill

        # ── 5. 시리즈 번호 ─────────────────────────────────────────────
        if series_number is not None and f_series:
            _stroke_center(draw, f"Space Journey #{series_number:03d}", y_series,
                           f_series, W, fill=(200, 200, 200, 180), sc=sc, sw=2)

        # ── 6. 한글 메인 텍스트 (카테고리 컬러) ────────────────────────
        _stroke_center(draw, l1, y_ko, f_ko, W, fill=(*cat_rgb, 255), sc=sc, sw=5)
        if l2:
            _stroke_center(draw, l2, y_ko + ko_line_h, f_ko, W,
                           fill=(*cat_rgb, 255), sc=sc, sw=5)

        # ── 7. 영문 서브 텍스트 ────────────────────────────────────────
        _stroke_center(draw, seo_en, y_en, f_en_sub, W,
                       fill=(230, 230, 230, 215), sc=sc, sw=3)

        # ── 8. 필 배지: "1 Hour Ambient Sound" ─────────────────────────
        _draw_pill_badge(draw, "1 Hour Ambient Sound", W // 2, y_pill, cat_rgb, f_pill)

        # ── 9. 1 HOUR 원형 배지 (좌상단) ───────────────────────────────
        _draw_hour_badge(draw, 18, 18, cat_rgb)

        # ── 10. 로고 (우상단 헤딩 + 우하단 원형) ───────────────────────
        base = _paste_logo_tr(base)
        base = _paste_logo_br(base)

        # ── 11. 저장 ───────────────────────────────────────────────────
        slug  = seo_ko.replace(" ", "_")[:20]
        fname = output_name or f"thumb_cosmic_ko_{slug}_{random.randint(1000, 9999)}.jpg"
        out   = self.thumb_dir / fname
        base.convert("RGB").save(out, "JPEG", quality=95)
        log.info(f"Thumbnail (cosmic-ko / {seo_ko}) saved: {out.name}")
        return out
