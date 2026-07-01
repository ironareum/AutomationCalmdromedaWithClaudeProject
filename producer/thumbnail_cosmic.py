"""
Cosmic Pipeline Thumbnail Generator
2026.06.30 신규 레이아웃 — 상단 킥커 라벨 + 그라데이션 라인, 골드 2줄 제목,
고정 서브타이틀, 하단 그라데이션 라인, 좌하단 로고 (사용자 레퍼런스 이미지 기반)

[설계 원칙]
  - producer/thumbnail.py (자연소리 파이프라인) 수정 금지
  - emotion_copy: pipeline_cosmic.py에서 concept["longform_emotional"] 전달
"""

import logging
import random
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

_BASE     = Path(__file__).parent.parent
FONTS_DIR = _BASE / "assets" / "fonts"
LOGO_PATH = _BASE / "assets" / "logo_cosmic.png"

GOLD         = (212, 175, 55)    # #D4AF37
OUTLINE      = (58, 42, 13)      # #3A2A0D
SHADOW       = (0, 0, 0)
SHADOW_ALPHA = 153                # rgba(0,0,0,0.6)
DARK_PURPLE  = (30, 10, 60)

KICKER_TEXT = "우 주  수 면 음 악"
SUBTITLE_TEXT = "고요한 우주가 당신의 밤을 감싸줍니다"


def _resolve_font(filename: str) -> str:
    for p in [FONTS_DIR / filename, Path("/mnt/user-data/uploads") / filename]:
        if p.exists():
            return str(p)
    raise FileNotFoundError(f"폰트 없음: {filename} — assets/fonts/ 에 넣어주세요")


def _load_kicker_font(size: int) -> ImageFont.FreeTypeFont:
    """킥커용: Pretendard-Regular → RIDIBatang 폴백"""
    for fn in ["Pretendard-Regular.ttf", "RIDIBatang.otf"]:
        try:
            return ImageFont.truetype(_resolve_font(fn), size)
        except FileNotFoundError:
            continue
    raise RuntimeError("킥커 폰트 없음")


def _load_title_font(size: int) -> ImageFont.FreeTypeFont:
    """제목용: NanumMyeongjo → NanumMyeongjoExtraBold → RIDIBatang 폴백"""
    for fn in ["NanumMyeongjo.ttf", "NanumMyeongjoExtraBold.ttf", "RIDIBatang.otf"]:
        try:
            return ImageFont.truetype(_resolve_font(fn), size)
        except FileNotFoundError:
            continue
    raise RuntimeError("제목 폰트 없음")


def _load_subtitle_font(size: int) -> ImageFont.FreeTypeFont:
    """서브타이틀용: Pretendard-ExtraLight → Pretendard-Regular → RIDIBatang 폴백"""
    for fn in ["Pretendard-ExtraLight.ttf", "Pretendard-Regular.ttf", "RIDIBatang.otf"]:
        try:
            return ImageFont.truetype(_resolve_font(fn), size)
        except FileNotFoundError:
            continue
    raise RuntimeError("서브타이틀 폰트 없음")


def _split_two_lines(text: str) -> tuple[str, str]:
    text = text.strip()
    spaces = [i for i, c in enumerate(text) if c == " "]
    if not spaces:
        return text, ""
    mid = len(text) // 2
    sp = min(spaces, key=lambda x: abs(x - mid))
    return text[:sp].strip(), text[sp:].strip()


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


def _draw_styled_text(draw, text, x, y, font, shadow_offset=3, outline_w=2):
    """그림자(rgba(0,0,0,0.6)) → 외곽선(#3A2A0D) → 본문(#D4AF37) 순으로 그린다."""
    draw.text((x + shadow_offset, y + shadow_offset), text, font=font,
              fill=(*SHADOW, SHADOW_ALPHA))
    for dx in range(-outline_w, outline_w + 1):
        for dy in range(-outline_w, outline_w + 1):
            if dx == 0 and dy == 0:
                continue
            draw.text((x + dx, y + dy), text, font=font, fill=(*OUTLINE, 255))
    draw.text((x, y), text, font=font, fill=(*GOLD, 255))


def _draw_sparkle(draw, cx: int, cy: int, size: int):
    """RIDIBatang에 '✦' 글리프가 없어 폴리곤으로 4갈래 반짝임 아이콘을 직접 그린다."""
    pts = [
        (cx, cy - size), (cx + size * 0.22, cy - size * 0.22),
        (cx + size, cy), (cx + size * 0.22, cy + size * 0.22),
        (cx, cy + size), (cx - size * 0.22, cy + size * 0.22),
        (cx - size, cy), (cx - size * 0.22, cy - size * 0.22),
    ]
    draw.polygon(pts, fill=(*GOLD, 255))


def _draw_fading_line(base: Image.Image, x: int, y: int, width: int, height: int = 2):
    """좌측이 진하고 우측으로 갈수록 사라지는 골드 그라데이션 라인."""
    if width <= 0:
        return
    line_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ld = ImageDraw.Draw(line_img)
    for i in range(width):
        a = int(220 * (1 - i / width))
        ld.line([(i, 0), (i, height - 1)], fill=(*GOLD, a))
    base.alpha_composite(line_img, (x, y))


class CosmicThumbnailGenerator:
    """코스믹 파이프라인 전용 썸네일 — 킥커 라벨 + 골드 제목 + 서브타이틀 + 로고."""

    SIZE = (1280, 720)

    def __init__(self, work_dir: Path):
        self.thumb_dir = work_dir / "thumbnails"
        self.thumb_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        video_path:   Path | None = None,
        emotion_copy: str = "",
        output_name:  str | None = None,
    ) -> Path:
        """
        영상 첫 프레임을 배경으로 감성 문구 2줄 썸네일 생성.
        프레임 추출 실패 시 다크 폴백.
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
            log.info("썸네일 배경: 다크 폴백")

        return self._render(bg, emotion_copy, output_name)

    def _render(
        self,
        bg:           Image.Image | None,
        emotion_copy: str,
        output_name:  str | None,
    ) -> Path:
        W, H = self.SIZE
        pad_x = int(W * 0.07)   # 좌측 여백 7% — 모든 텍스트/라인/로고 시작점

        # ── 1. 배경 ────────────────────────────────────────────────────
        if bg:
            base = bg.resize((W, H), Image.LANCZOS).convert("RGBA")
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            od = ImageDraw.Draw(ov)
            for yi in range(H):
                a = int(110 + 110 * yi / H)
                od.line([(0, yi), (W, yi)], fill=(0, 0, 0, a))
            base = Image.alpha_composite(base, ov)
        else:
            base = Image.new("RGBA", (W, H), (8, 4, 20, 255))

        # ── 2. 다크 퍼플 글로우 (좌상단 집중) ─────────────────────────
        gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gl)
        gx, gy = W // 3, H // 2
        for r in range(400, 0, -40):
            a = int(15 * (1 - r / 400))
            gd.ellipse([(gx - r * 2, gy - r), (gx + r * 2, gy + r)],
                       fill=(*DARK_PURPLE, a))
        base = Image.alpha_composite(base, gl)
        draw = ImageDraw.Draw(base)

        # ── 3. 상단 킥커 라벨 + 별 아이콘 + 그라데이션 라인 ───────────
        kicker_font = _load_kicker_font(26)
        ky = int(H * 0.135)
        _draw_styled_text(draw, KICKER_TEXT, pad_x, ky, kicker_font)
        kb = draw.textbbox((pad_x, ky), KICKER_TEXT, font=kicker_font)
        star_cx = kb[2] + 28
        star_cy = ky + 12
        _draw_sparkle(draw, star_cx, star_cy, size=9)

        line_y = ky + 14
        line_start_x = star_cx + 22
        line_end_x = int(W * 0.46)
        _draw_fading_line(base, line_start_x, line_y, line_end_x - line_start_x)
        draw = ImageDraw.Draw(base)

        # ── 4. 메인 타이틀 2줄 (감성 문구) ─────────────────────────────
        l1, l2 = _split_two_lines(emotion_copy)
        longer = l1 if len(l1) >= len(l2) else l2

        max_w = int(W * 0.86)
        title_size = 64
        for size in range(64, 39, -1):
            fnt = _load_title_font(size)
            dummy_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
            bbox = dummy_draw.textbbox((0, 0), longer, font=fnt)
            if (bbox[2] - bbox[0]) <= max_w:
                title_size = size
                break

        title_font = _load_title_font(title_size)
        line_h = int(title_size * 1.18)
        ty = int(H * 0.235)

        _draw_styled_text(draw, l1, pad_x, ty, title_font)
        if l2:
            _draw_styled_text(draw, l2, pad_x, ty + line_h, title_font)

        # ── 5. 서브타이틀 (고정 문구, 골드 통일) ──────────────────────
        sub_font = _load_subtitle_font(24)
        sub_y = ty + line_h * 2 + 28
        _draw_styled_text(draw, SUBTITLE_TEXT, pad_x, sub_y, sub_font)

        # ── 6. 하단 그라데이션 디바이더 ────────────────────────────────
        div_y = sub_y + 50
        div_w = int(W * 0.40)
        _draw_fading_line(base, pad_x, div_y, div_w, height=1)

        # ── 7. 로고 (좌하단, 텍스트 시작점과 좌측 정렬) ───────────────
        # logo_cosmic.png는 원형 배지 둘레에 투명 여백이 넓게 있어 원본 그대로
        # pad_x에 붙이면 보이는 원이 텍스트보다 한참 오른쪽에서 시작한다.
        # 알파 채널 기준으로 실제 보이는 영역만 잘라낸 뒤 정렬한다.
        if LOGO_PATH.exists():
            logo = Image.open(LOGO_PATH).convert("RGBA")
            visible_mask = logo.split()[3].point(lambda a: 255 if a > 30 else 0)
            bbox = visible_mask.getbbox()
            if bbox:
                logo = logo.crop(bbox)
            logo_h = int(H * 0.20)
            ratio = logo_h / logo.height
            logo_w = int(logo.width * ratio)
            logo_resized = logo.resize((logo_w, logo_h), Image.LANCZOS)
            logo_y = H - logo_h - int(H * 0.06)
            base.alpha_composite(logo_resized, (pad_x, logo_y))
        else:
            log.warning(f"로고 파일 없음: {LOGO_PATH}")

        # ── 8. 저장 ────────────────────────────────────────────────────
        slug = emotion_copy.replace(" ", "_")[:20]
        fname = output_name or f"thumb_cosmic_{slug}_{random.randint(1000, 9999)}.jpg"
        out = self.thumb_dir / fname
        base.convert("RGB").save(out, "JPEG", quality=95)
        log.info(f"Thumbnail saved: {out.name} / emotion: {emotion_copy}")
        return out
