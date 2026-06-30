"""
Cosmic Pipeline Thumbnail Generator
구 _render_cosmic() 스타일 복원 — 감성 문구 2줄, 좌정렬, 노랑 #FFE135, RIDIBatang

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

YELLOW       = (255, 225, 53)   # #FFE135
DARK_PURPLE  = (30, 10, 60)


def _resolve_font(filename: str) -> str:
    for p in [FONTS_DIR / filename, Path("/mnt/user-data/uploads") / filename]:
        if p.exists():
            return str(p)
    raise FileNotFoundError(f"폰트 없음: {filename} — assets/fonts/ 에 넣어주세요")


def _load_ko_font(size: int) -> ImageFont.FreeTypeFont:
    """RIDIBatang → NanumMyeongjoExtraBold → NanumMyeongjoBold 순 시도"""
    for fn in ["RIDIBatang.otf", "NanumMyeongjoExtraBold.ttf", "NanumMyeongjoBold.ttf"]:
        try:
            return ImageFont.truetype(_resolve_font(fn), size)
        except FileNotFoundError:
            continue
    raise RuntimeError("사용 가능한 한글 폰트 없음")


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


class CosmicThumbnailGenerator:
    """코스믹 파이프라인 전용 썸네일 — 구 _render_cosmic() 스타일."""

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
        pad_x = int(W * 0.06)   # 좌측 여백 6%
        pad_y = int(H * 0.11)   # 상단 여백 11%

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

        # ── 3. 텍스트: 좌정렬, 노랑 #FFE135, RIDIBatang, size 40~52 ──
        l1, l2 = _split_two_lines(emotion_copy)
        longer = l1 if len(l1) >= len(l2) else l2

        max_w = int(W * 0.88)
        font_size = 52
        for size in range(52, 39, -1):
            try:
                fnt = _load_ko_font(size)
                dummy_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
                bbox = dummy_draw.textbbox((0, 0), longer, font=fnt)
                if (bbox[2] - bbox[0]) <= max_w:
                    font_size = size
                    break
            except Exception:
                pass

        fnt = _load_ko_font(font_size)
        line_h = int(font_size * 1.35)
        sw = 4

        def draw_line(text: str, y: int):
            sc = (10, 5, 30)
            for dx in range(-sw, sw + 1):
                for dy in range(-sw, sw + 1):
                    if dx == 0 and dy == 0:
                        continue
                    if abs(dx) + abs(dy) > sw + 1:
                        continue
                    draw.text((pad_x + dx, y + dy), text, font=fnt, fill=(*sc, 200))
            draw.text((pad_x, y), text, font=fnt, fill=(*YELLOW, 255))

        draw_line(l1, pad_y)
        if l2:
            draw_line(l2, pad_y + line_h)

        # ── 4. 저장 (로고 없음) ────────────────────────────────────────
        slug = emotion_copy.replace(" ", "_")[:20]
        fname = output_name or f"thumb_cosmic_{slug}_{random.randint(1000, 9999)}.jpg"
        out = self.thumb_dir / fname
        base.convert("RGB").save(out, "JPEG", quality=95)
        log.info(f"Thumbnail saved: {out.name} / emotion: {emotion_copy}")
        return out
