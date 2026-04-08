"""
2026.03.26 Thumbnail Generator
2026.03.28 Pillow로 유튜브 썸네일 자동 생성 (1280x720)
2026.03.28 Calmdromeda 로고 자동 삽입
2026.03.28 한글 타이틀 지원
2026.03.29 로고 워터마크 자동 삽입 / 한글 지원
2026.03.29 영상 첫 프레임 자동 배경
2026.03.29 배경 dominant color 기반 stroke 텍스트
2026.03.29 RIDIBatang(한글) + Bitter Italic(영문) 폰트

Thumbnail Generator
- | 기준으로 첫 파트만 썸네일 타이틀 사용
- 실제 픽셀 측정으로 폰트 크기 자동 조정 (절대 잘리지 않음)
- 배경: 영상 첫 프레임 자동 추출
- stroke 텍스트: 배경 dominant color 기반 테두리
- RIDIBatang(한글) + Bitter Italic(영문)
- 좌상단 heading 로고 + 우하단 원형 로고

[폰트 파일 위치] assets/fonts/
[로고 파일 위치] assets/
  logo_heading.png (← Heading_2_.png)
  logo.png         (← Calmdromeda.PNG)

2026.03.30 신규 신규 카테고리 추가(12개)
2026.04.08 fix: 타이틀 한글/영문 분리
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


# ── 폰트 ──────────────────────────────────────────────────────────────
def _resolve(filename: str) -> str:
    for p in [FONTS_DIR / filename, Path("/mnt/user-data/uploads") / filename]:
        if p.exists():
            return str(p)
    raise FileNotFoundError(f"폰트 없음: {filename} → assets/fonts/ 에 넣어주세요")


def _fko(size):  return ImageFont.truetype(_resolve("RIDIBatang.otf"), size)


def _fen(size, style="italic"):
    return ImageFont.truetype(_resolve({
        "bold":"Bitter-Bold.ttf","regular":"Bitter-Regular.ttf","italic":"Bitter-Italic.ttf"
    }[style]), size)


# ── 로고 ──────────────────────────────────────────────────────────────
def _rm_black(img: Image.Image, thr=45) -> Image.Image:
    img = img.convert("RGBA")
    px  = img.load()
    for y in range(img.height):
        for x in range(img.width):
            r,g,b,a = px[x,y]
            if r<thr and g<thr and b<thr: px[x,y]=(r,g,b,0)
    return img


def _paste_logo_tl(base: Image.Image) -> Image.Image:
    """좌상단 Heading 로고"""
    if not LOGO_HEADING.exists():
        log.warning(f"logo_heading.png 없음: {LOGO_HEADING}")
        return base
    W, H = base.size
    logo = _rm_black(Image.open(LOGO_HEADING))
    tw   = int(W * 0.17)
    th   = int(logo.height * tw / logo.width)
    logo = logo.resize((tw, th), Image.LANCZOS)
    layer = Image.new("RGBA", (W,H), (0,0,0,0))
    layer.paste(logo, (8,8), logo)
    return Image.alpha_composite(base.convert("RGBA"), layer)

def _paste_logo_br(base: Image.Image) -> Image.Image:
    """우하단 원형 로고"""
    if not LOGO_CIRCLE.exists():
        return base
    W, H = base.size
    logo  = _rm_black(Image.open(LOGO_CIRCLE))
    sz    = 70
    logo  = logo.resize((sz,sz), Image.LANCZOS)
    r,g,b,a = logo.split()
    logo.putalpha(a.point(lambda v: int(v*0.65)))
    layer = Image.new("RGBA", (W,H), (0,0,0,0))
    layer.paste(logo, (W-sz-12, H-sz-12), logo)
    return Image.alpha_composite(base.convert("RGBA"), layer)


# ── 영상 첫 프레임 ─────────────────────────────────────────────────────
def _extract_frame(video: Path, out: Path, sec=3) -> bool:
    try:
        r = subprocess.run(
            ["ffmpeg","-y","-ss",str(sec),"-i",str(video),
             "-vframes","1","-q:v","2",str(out)],
            capture_output=True, encoding="utf-8", errors="replace", timeout=30)
        return out.exists() and out.stat().st_size > 0
    except Exception as e:
        log.warning(f"프레임 추출 실패: {e}")
        return False


# ── Dominant → Stroke 색상 ────────────────────────────────────────────
def _stroke_color(img: Image.Image) -> tuple:
    W,H = img.size
    crop  = img.crop((W//4, H//4, W*3//4, H*3//4))
    small = crop.resize((16,16), Image.LANCZOS).convert("RGB")
    px = list(small.getdata())
    r = sum(p[0] for p in px)//len(px)
    g = sum(p[1] for p in px)//len(px)
    b = sum(p[2] for p in px)//len(px)
    return tuple(min(int(c*0.22), 55) for c in (r,g,b))


# ── 폰트 크기 자동 조정 ────────────────────────────────────────────────
def _fit_font_size(text: str, max_px: int,
                   max_size=100, min_size=38) -> int:
    """text가 max_px 너비 안에 들어오는 최대 폰트 크기 반환 (실제 픽셀 측정)"""
    dummy_img  = Image.new("RGB", (1,1))
    dummy_draw = ImageDraw.Draw(dummy_img)
    for size in range(max_size, min_size-1, -2):
        try:
            fnt  = _fko(size)
            bbox = dummy_draw.textbbox((0,0), text, font=fnt)
            if (bbox[2]-bbox[0]) <= max_px:
                return size
        except:
            pass
    return min_size


# ── 타이틀 2줄 분할 ────────────────────────────────────────────────────
def _split_two_lines(text: str):
    """공백 기준으로 중간에서 가장 가까운 위치에서 2줄 분할"""
    text   = text.strip()
    spaces = [i for i,c in enumerate(text) if c==" "]
    if not spaces:
        return text, ""
    mid = len(text)//2
    sp  = min(spaces, key=lambda x: abs(x-mid))
    return text[:sp].strip(), text[sp:].strip()


# ── Stroke 텍스트 렌더링 ───────────────────────────────────────────────
def _stroke_center(draw, text, y, fnt, W,
                   fill=(255,255,255), sc=(20,20,20), sw=5):
    bbox = draw.textbbox((0,0), text, font=fnt)
    x    = (W-(bbox[2]-bbox[0]))//2
    for dx in range(-sw, sw+1):
        for dy in range(-sw, sw+1):
            if dx==0 and dy==0: continue
            if abs(dx)+abs(dy) > sw+2: continue
            draw.text((x+dx, y+dy), text, font=fnt, fill=(*sc,225))
    draw.text((x,y), text, font=fnt, fill=fill)


# ── 테마 ──────────────────────────────────────────────────────────────
THEMES = {
    "rain":           dict(ov=150, glow=(65,118,250),  sub=(170,205,255), en=(115,172,255)),
    "rain_thunder":   dict(ov=160, glow=(100,60,220),  sub=(190,170,255), en=(150,130,245)),
    "ocean":          dict(ov=148, glow=(50,172,218),  sub=(145,212,238), en=(85,195,228)),
    "forest":         dict(ov=145, glow=(90,190,55),   sub=(185,245,145), en=(135,225,95)),
    "birds":          dict(ov=140, glow=(160,210,80),  sub=(210,245,160), en=(165,225,110)),
    "white_noise":    dict(ov=155, glow=(160,160,210), sub=(210,210,240), en=(170,170,230)),
    "cafe":           dict(ov=148, glow=(210,155,75),  sub=(240,220,180), en=(220,175,105)),
    "camping":        dict(ov=150, glow=(235,135,55),  sub=(248,218,175), en=(238,165,95)),
    "sleep":          dict(ov=150, glow=(125,65,215),  sub=(192,172,255), en=(168,132,242)),
    # 신규 카테고리
    "airplane":       dict(ov=155, glow=(100,140,200), sub=(180,210,240), en=(140,180,225)),
    "subway":         dict(ov=158, glow=(80,80,140),   sub=(160,160,200), en=(120,120,180)),
    "library":        dict(ov=148, glow=(160,120,70),  sub=(220,200,160), en=(190,165,115)),
    "underwater":     dict(ov=150, glow=(30,150,180),  sub=(120,210,230), en=(60,185,210)),
    "hot_spring":     dict(ov=145, glow=(200,100,80),  sub=(240,190,170), en=(220,145,125)),
    "fireplace_rain": dict(ov=152, glow=(220,100,40),  sub=(245,195,145), en=(230,140,80)),
    "summer_night":   dict(ov=148, glow=(80,160,100),  sub=(160,230,180), en=(110,200,140)),
    "winter_snow":    dict(ov=145, glow=(160,200,230), sub=(210,230,245), en=(180,215,238)),
    "study_room":     dict(ov=150, glow=(180,150,80),  sub=(230,215,170), en=(205,180,120)),
    "stream":         dict(ov=145, glow=(60,180,140),  sub=(140,225,200), en=(90,205,170)),
    "summer_rain":    dict(ov=148, glow=(80,160,80),   sub=(160,220,160), en=(100,190,120)),
    "snow_walk":      dict(ov=143, glow=(180,210,240), sub=(220,235,250), en=(195,220,245)),
}


class ThumbnailGenerator:
    SIZE = (1280, 720)

    def __init__(self, work_dir: Path):
        self.work_dir  = work_dir
        self.thumb_dir = work_dir / "thumbnails"
        self.thumb_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        title:       str,
        category:    str,
        video_path:  Path | None = None,
        title_sub:   str = "잠잘때 듣기 좋은",
        subtitle_en: str = "Healing Music",
        output_name: str | None = None,
    ) -> Path:
        W, H = self.SIZE
        t    = THEMES.get(category, THEMES["forest"])

        # ── 1. 타이틀 파싱 ──────────────────────────────────────────
        # "새소리 ASMR | 틀어두면 머리가 맑아지는 소리 | Bird Sounds - Sleep Music Nature"
        # → 파이프[0] = 한글 타이틀, 파이프[2] = 영문 SEO
        title_parts = [p.strip() for p in title.split("|")]
        display    = title_parts[0] if title_parts else title
        # 파이프[2]에서 대시(-) 앞부분만 썸네일 영문 보조로 사용
        # "Bird Sounds - Sleep Music Nature" → "Bird Sounds"
        raw_en     = title_parts[2] if len(title_parts) >= 3 else ""
        display_en = raw_en.split("-")[0].strip() if raw_en else ""

        # 2줄 분할
        l1, l2 = _split_two_lines(display)
        longer = l1 if len(l1) >= len(l2) else l2

        # 폰트 크기: W*82% 안에 확실히 들어오도록 실측
        max_w     = int(W * 0.82)
        font_size = _fit_font_size(longer, max_w, max_size=100, min_size=38)
        log.info(f"타이틀: \"{display}\" + en:\"{display_en}\" → {font_size}px  ({l1!r} / {l2!r})")

        # ── 2. 배경 (영상 첫 프레임) ────────────────────────────────
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
            log.info("썸네일 배경: 그라디언트 폴백")

        sc = _stroke_color(bg) if bg else (15,15,15)
        log.info(f"Stroke 색상: RGB{sc}")

        # ── 3. 배경 합성 ────────────────────────────────────────────
        if bg:
            base = bg.resize((W,H), Image.LANCZOS).convert("RGBA")
            ov   = Image.new("RGBA",(W,H),(0,0,0,0))
            od   = ImageDraw.Draw(ov)
            for y in range(H):
                a = int(t["ov"]*0.60 + t["ov"]*0.40*y/H)
                od.line([(0,y),(W,y)], fill=(0,0,0,a))
            base = Image.alpha_composite(base, ov)
        else:
            base = Image.new("RGBA",(W,H),(15,35,15,255))

        # ── 4. 글로우 ───────────────────────────────────────────────
        gl = Image.new("RGBA",(W,H),(0,0,0,0))
        gd = ImageDraw.Draw(gl)
        cx, cy = W//2, H//2-10
        for r in range(260,0,-26):
            a = int(14*(1-r/260))
            gd.ellipse([(cx-r*2,cy-r),(cx+r*2,cy+r)], fill=(*t["glow"],a))
        base = Image.alpha_composite(base.convert("RGBA"), gl)
        draw = ImageDraw.Draw(base)

        # ── 5. 레이아웃 계산 ────────────────────────────────────────
        f_sub    = _fko(28)
        f_main   = _fko(font_size)
        f_en_sub = _fen(26, "regular")   # 영문 보조 (작게)
        f_en     = _fen(48, "italic")    # 이탤릭 감성 문구

        sub_h    = f_sub.getbbox("A")[3]    + 8   # 부제목 높이
        line_h   = int(font_size * 1.18)          # 메인 타이틀 줄 높이
        en_sub_h = f_en_sub.getbbox("A")[3] + 6   # 영문 보조 높이
        en_h     = f_en.getbbox("A")[3]     + 8   # 영문 서브 높이
        gap      = 14                             # 요소 간격

        n_lines = 2 if l2 else 1
        # 영문 보조 있을 때만 높이 포함
        en_sub_total = (en_sub_h + gap) if display_en else 0
        total_h = sub_h + gap + line_h*n_lines + en_sub_total + gap + en_h
        y_start = (H - total_h) // 2

        y_sub   = y_start
        y_l1    = y_sub + sub_h + gap
        y_l2    = y_l1 + line_h
        after_main = y_l2 + line_h if l2 else y_l1 + line_h
        y_en_sub = after_main + 4 if display_en else after_main
        y_en     = (y_en_sub + en_sub_h + gap) if display_en else (after_main + gap)

        # ── 6. 부제목 ────────────────────────────────────────────────
        _stroke_center(draw, title_sub, y_sub, f_sub, W,
                       fill=(*t["sub"],210), sc=sc, sw=3)

        # 구분선
        draw.line([(W//2-45, y_sub+sub_h+4), (W//2+45, y_sub+sub_h+4)],
                  fill=(*t["glow"],70), width=1)

        # ── 7. 메인 타이틀 (한글) ───────────────────────────────────
        _stroke_center(draw, l1, y_l1, f_main, W,
                       fill=(255,255,255), sc=sc, sw=6)
        if l2:
            _stroke_center(draw, l2, y_l2, f_main, W,
                           fill=(255,255,255), sc=sc, sw=6)

        # ── 7-1. 영문 보조 (작게, 회색) ─────────────────────────────
        if display_en:
            _stroke_center(draw, display_en, y_en_sub, f_en_sub, W,
                           fill=(200,200,200,180), sc=sc, sw=2)

        # ── 8. 이탤릭 감성 문구 ──────────────────────────────────────
        _stroke_center(draw, subtitle_en, y_en, f_en, W,
                       fill=(*t["en"],225), sc=sc, sw=4)

        # ── 9. 로고 ─────────────────────────────────────────────────
        base = _paste_logo_tl(base)
        base = _paste_logo_br(base)

        # ── 10. 저장 ─────────────────────────────────────────────────
        fname = output_name or f"thumb_{category}_{random.randint(1000,9999)}.jpg"
        out   = self.thumb_dir / fname
        base.convert("RGB").save(out, "JPEG", quality=95)
        log.info(f"Thumbnail saved: {out.name}")
        return out
    def generate_from_image(
        self,
        title:       str,
        category:    str,
        image_path:  Path,
        title_sub:   str = "잠잘때 듣기 좋은",
        subtitle_en: str = "Healing Music",
        output_name: str | None = None,
    ) -> Path:
        """이미지 파일을 배경으로 썸네일 생성 (jpg/png 지원)"""
        from PIL import Image as PILImage
        W, H = self.SIZE
        t    = THEMES.get(category, THEMES["forest"])

        display = title.split("|")[0].strip() if "|" in title else title
        l1, l2  = _split_two_lines(display)
        longer  = l1 if len(l1) >= len(l2) else l2
        max_w   = int(W * 0.82)
        font_size = _fit_font_size(longer, max_w, max_size=100, min_size=38)
        log.info(f"타이틀: \"{display}\" → {font_size}px  ({l1!r} / {l2!r})")

        # 이미지 배경 로드
        try:
            bg = PILImage.open(image_path).convert("RGB")
            log.info(f"썸네일 배경: {image_path.name} (이미지)")
        except Exception as e:
            log.warning(f"이미지 로드 실패: {e}")
            bg = None

        sc   = _stroke_color(bg) if bg else (15,15,15)
        log.info(f"Stroke 색상: RGB{sc}")

        if bg:
            base = bg.resize((W,H), PILImage.LANCZOS).convert("RGBA")
            ov   = PILImage.new("RGBA",(W,H),(0,0,0,0))
            od   = ImageDraw.Draw(ov)
            for y in range(H):
                a = int(t["ov"]*0.60 + t["ov"]*0.40*y/H)
                od.line([(0,y),(W,y)], fill=(0,0,0,a))
            base = Image.alpha_composite(base, ov)
        else:
            base = Image.new("RGBA",(W,H),(15,35,15,255))

        gl = Image.new("RGBA",(W,H),(0,0,0,0))
        gd = ImageDraw.Draw(gl)
        cx, cy = W//2, H//2-10
        for r in range(260,0,-26):
            a = int(14*(1-r/260))
            gd.ellipse([(cx-r*2,cy-r),(cx+r*2,cy+r)], fill=(*t["glow"],a))
        base = Image.alpha_composite(base.convert("RGBA"), gl)
        draw = ImageDraw.Draw(base)

        f_sub  = _fko(28)
        f_main = _fko(font_size)
        f_en   = _fen(48, "italic")
        sub_h  = f_sub.getbbox("A")[3]  + 8
        line_h = int(font_size * 1.18)
        en_h   = f_en.getbbox("A")[3]   + 8
        gap    = 18
        n_lines = 2 if l2 else 1
        total_h = sub_h + gap + line_h*n_lines + gap + en_h
        y_start = (H - total_h) // 2
        y_sub  = y_start
        y_l1   = y_sub + sub_h + gap
        y_l2   = y_l1 + line_h
        y_en   = (y_l2 + line_h if l2 else y_l1 + line_h) + gap

        _stroke_center(draw, title_sub, y_sub, f_sub, W,
                       fill=(*t["sub"],210), sc=sc, sw=3)
        draw.line([(W//2-45, y_sub+sub_h+4), (W//2+45, y_sub+sub_h+4)],
                  fill=(*t["glow"],70), width=1)
        _stroke_center(draw, l1, y_l1, f_main, W,
                       fill=(255,255,255), sc=sc, sw=6)
        if l2:
            _stroke_center(draw, l2, y_l2, f_main, W,
                           fill=(255,255,255), sc=sc, sw=6)
        _stroke_center(draw, subtitle_en, y_en, f_en, W,
                       fill=(*t["en"],225), sc=sc, sw=4)

        base = _paste_logo_tl(base)
        base = _paste_logo_br(base)

        fname = output_name or f"thumb_{category}_{random.randint(1000,9999)}.jpg"
        out   = self.thumb_dir / fname
        base.convert("RGB").save(out, "JPEG", quality=95)
        log.info(f"Thumbnail saved: {out.name}")
        return out


    def generate_from_image(
        self,
        title:       str,
        category:    str,
        image_path,
        title_sub:   str = "잠잘때 듣기 좋은",
        subtitle_en: str = "Healing Music",
        output_name = None,
    ):
        """이미지 파일을 배경으로 썸네일 생성"""
        W, H = self.SIZE
        t    = THEMES.get(category, THEMES["forest"])

        display   = title.split("|")[0].strip() if "|" in title else title
        l1, l2    = _split_two_lines(display)
        longer    = l1 if len(l1) >= len(l2) else l2
        font_size = _fit_font_size(longer, int(W*0.82), max_size=100, min_size=38)
        log.info(f"타이틀: \"{display}\" → {font_size}px  ({l1!r} / {l2!r})")

        try:
            bg = Image.open(image_path).convert("RGB")
            log.info(f"썸네일 배경: {image_path} (이미지)")
        except Exception as e:
            log.warning(f"이미지 로드 실패: {e}")
            bg = None

        sc = _stroke_color(bg) if bg else (15, 15, 15)
        log.info(f"Stroke 색상: RGB{sc}")

        if bg:
            base = bg.resize((W, H), Image.LANCZOS).convert("RGBA")
            ov   = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            od   = ImageDraw.Draw(ov)
            for y in range(H):
                a = int(t["ov"]*0.60 + t["ov"]*0.40*y/H)
                od.line([(0, y), (W, y)], fill=(0, 0, 0, a))
            base = Image.alpha_composite(base, ov)
        else:
            base = Image.new("RGBA", (W, H), (15, 35, 15, 255))

        gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gl)
        cx, cy = W//2, H//2-10
        for r in range(260, 0, -26):
            a = int(14*(1-r/260))
            gd.ellipse([(cx-r*2, cy-r), (cx+r*2, cy+r)], fill=(*t["glow"], a))
        base = Image.alpha_composite(base.convert("RGBA"), gl)
        draw = ImageDraw.Draw(base)

        f_sub  = _fko(28)
        f_main = _fko(font_size)
        f_en   = _fen(48, "italic")
        sub_h  = f_sub.getbbox("A")[3] + 8
        line_h = int(font_size * 1.18)
        en_h   = f_en.getbbox("A")[3]  + 8
        gap    = 18
        n_lines = 2 if l2 else 1
        total_h = sub_h + gap + line_h*n_lines + gap + en_h
        y_start = (H - total_h) // 2
        y_sub   = y_start
        y_l1    = y_sub + sub_h + gap
        y_l2    = y_l1 + line_h
        y_en    = (y_l2 + line_h if l2 else y_l1 + line_h) + gap

        _stroke_center(draw, title_sub, y_sub, f_sub, W,
                       fill=(*t["sub"], 210), sc=sc, sw=3)
        draw.line([(W//2-45, y_sub+sub_h+4), (W//2+45, y_sub+sub_h+4)],
                  fill=(*t["glow"], 70), width=1)
        _stroke_center(draw, l1, y_l1, f_main, W,
                       fill=(255, 255, 255), sc=sc, sw=6)
        if l2:
            _stroke_center(draw, l2, y_l2, f_main, W,
                           fill=(255, 255, 255), sc=sc, sw=6)
        _stroke_center(draw, subtitle_en, y_en, f_en, W,
                       fill=(*t["en"], 225), sc=sc, sw=4)

        base = _paste_logo_tl(base)
        base = _paste_logo_br(base)

        fname = output_name or f"thumb_{category}_{random.randint(1000,9999)}.jpg"
        out   = self.thumb_dir / fname
        base.convert("RGB").save(out, "JPEG", quality=95)
        log.info(f"Thumbnail saved: {out.name}")
        return out
    def generate_from_image(
        self,
        title:       str,
        category:    str,
        image_path:  Path,
        title_sub:   str = "잠잘때 듣기 좋은",
        subtitle_en: str = "Healing Music",
        output_name: str | None = None,
    ) -> Path:
        """이미지 파일을 배경으로 썸네일 생성 (jpg/png 지원)"""
        from PIL import Image as PILImage
        W, H = self.SIZE
        t    = THEMES.get(category, THEMES["forest"])

        display = title.split("|")[0].strip() if "|" in title else title
        l1, l2  = _split_two_lines(display)
        longer  = l1 if len(l1) >= len(l2) else l2
        max_w   = int(W * 0.82)
        font_size = _fit_font_size(longer, max_w, max_size=100, min_size=38)
        log.info(f"타이틀: \"{display}\" → {font_size}px  ({l1!r} / {l2!r})")

        # 이미지 배경 로드
        try:
            bg = PILImage.open(image_path).convert("RGB")
            log.info(f"썸네일 배경: {image_path.name} (이미지)")
        except Exception as e:
            log.warning(f"이미지 로드 실패: {e}")
            bg = None

        sc   = _stroke_color(bg) if bg else (15,15,15)
        log.info(f"Stroke 색상: RGB{sc}")

        if bg:
            base = bg.resize((W,H), PILImage.LANCZOS).convert("RGBA")
            ov   = PILImage.new("RGBA",(W,H),(0,0,0,0))
            od   = ImageDraw.Draw(ov)
            for y in range(H):
                a = int(t["ov"]*0.60 + t["ov"]*0.40*y/H)
                od.line([(0,y),(W,y)], fill=(0,0,0,a))
            base = Image.alpha_composite(base, ov)
        else:
            base = Image.new("RGBA",(W,H),(15,35,15,255))

        gl = Image.new("RGBA",(W,H),(0,0,0,0))
        gd = ImageDraw.Draw(gl)
        cx, cy = W//2, H//2-10
        for r in range(260,0,-26):
            a = int(14*(1-r/260))
            gd.ellipse([(cx-r*2,cy-r),(cx+r*2,cy+r)], fill=(*t["glow"],a))
        base = Image.alpha_composite(base.convert("RGBA"), gl)
        draw = ImageDraw.Draw(base)

        f_sub  = _fko(28)
        f_main = _fko(font_size)
        f_en   = _fen(48, "italic")
        sub_h  = f_sub.getbbox("A")[3]  + 8
        line_h = int(font_size * 1.18)
        en_h   = f_en.getbbox("A")[3]   + 8
        gap    = 18
        n_lines = 2 if l2 else 1
        total_h = sub_h + gap + line_h*n_lines + gap + en_h
        y_start = (H - total_h) // 2
        y_sub  = y_start
        y_l1   = y_sub + sub_h + gap
        y_l2   = y_l1 + line_h
        y_en   = (y_l2 + line_h if l2 else y_l1 + line_h) + gap

        _stroke_center(draw, title_sub, y_sub, f_sub, W,
                       fill=(*t["sub"],210), sc=sc, sw=3)
        draw.line([(W//2-45, y_sub+sub_h+4), (W//2+45, y_sub+sub_h+4)],
                  fill=(*t["glow"],70), width=1)
        _stroke_center(draw, l1, y_l1, f_main, W,
                       fill=(255,255,255), sc=sc, sw=6)
        if l2:
            _stroke_center(draw, l2, y_l2, f_main, W,
                           fill=(255,255,255), sc=sc, sw=6)
        _stroke_center(draw, subtitle_en, y_en, f_en, W,
                       fill=(*t["en"],225), sc=sc, sw=4)

        base = _paste_logo_tl(base)
        base = _paste_logo_br(base)

        fname = output_name or f"thumb_{category}_{random.randint(1000,9999)}.jpg"
        out   = self.thumb_dir / fname
        base.convert("RGB").save(out, "JPEG", quality=95)
        log.info(f"Thumbnail saved: {out.name}")
        return out