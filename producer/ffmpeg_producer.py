"""
FFmpeg Video Producer
2026.03.26 사운드 레이어링 + 영상 루프 합성 → 1~3시간 유튜브 영상 생성
2026.03.28 영상 우측 하단에 Calmdromeda 로고 워터마크 자동 삽입
2026.03.29 임시 파일 단계별 즉시 삭제 → 디스크 사용량 최소화
2026.03.29 오디오 -14 LUFS 정규화 (YouTube 권장)
2026.03.29 영상 좌상단 heading 로고 + 우하단 원형 로고 동시 삽입
2026.04.11 feat: 루프 경계 acrossfade 적용 — seamless loop 생성 (연결 부자연스러움 개선)

[디스크 사용 흐름]
  이전: 원본영상 + normalized + video_loop + mixed_audio + merged_no_logo + 최종 = 최종x3~4배
  이후: 원본영상 + mixed_audio(임시) + 최종 = 최종x1.1배 수준

[임시 파일 관리 전략]
  - normalized 클립: 합성 직후 삭제
  - video_loop: merge 완료 직후 삭제
  - mixed_audio: merge 완료 직후 삭제
  - merged_no_logo: 로고 적용 완료 직후 삭제
  - temp 폴더: 파이프라인 완료 후 전체 삭제
2026.03.29 오디오 -14 LUFS 정규화 (YouTube 권장)
2026.03.29 영상 좌상단 heading 로고 + 우하단 원형 로고 동시 삽입
2026.03.29 video 수집 개수 판정로직 변경
2026.03.30 최적화: 영상 CRF 28, fps 24, preset medium (이전값 주석 보관)(처리시간 단축, 영상 해상도/용량 최적화)
2026.04.04 feat: 3레이어 사운드 구조 (main/sub/point) + 볼륨 랜덤화 + calm 쿼리 강화
2026.04.07 fix: LUFS -14 → -18 (ASMR 힐링 채널 기준)

"""

import subprocess
import logging
import json
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

# 로고 파일 경로 (프로젝트 루트 기준)
LOGO_PATH         = Path(__file__).parent.parent / "assets" / "logo.png"           # 우하단 원형 로고
LOGO_HEADING_PATH = Path(__file__).parent.parent / "assets" / "logo_heading.png"   # 좌상단 가로형 로고


class VideoProducer:
    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self.temp_dir = work_dir / "temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._check_ffmpeg()

    def _check_ffmpeg(self):
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True,
                                    encoding="utf-8", errors="replace")
            log.info(f"FFmpeg ready: {result.stdout.split(chr(10))[0][:50]}")
        except FileNotFoundError:
            raise RuntimeError("FFmpeg not found. Install: https://ffmpeg.org/download.html")

    def _run(self, cmd: list, desc: str = "") -> bool:
        """FFmpeg 명령 실행"""
        log.info(f"FFmpeg: {desc}")
        log.debug(f"CMD: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace") #UnicodeDecodeError 보완. errors="replace" 가 한글 경로 때문에 생기는 디코딩 오류를 그냥 무시하고 넘어가게 해줘요.
        if result.returncode != 0:
            log.error(f"FFmpeg failed:\n{result.stderr[-800:]}") # 에러로그 출력 800자
            return False
        return True

    def _delete(self, *paths: Path):
        """임시 파일 즉시 삭제"""
        for p in paths:
            try:
                if p and p.exists():
                    p.unlink()
                    log.debug(f"Deleted temp: {p.name}")
            except Exception as e:
                log.warning(f"삭제 실패 {p}: {e}")

    def cleanup_temp(self):
        """temp 폴더 전체 삭제 (파이프라인 완료 후 호출)"""
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
                log.info(f"Temp folder deleted: {self.temp_dir}")
        except Exception as e:
            log.warning(f"Temp 폴더 삭제 실패: {e}")

    def _prepare_logo_png(self, logo_path: Path,
                          black_threshold: int = 45,
                          opacity: float = 0.85) -> Path:
        """
        Pillow로 로고 PNG 전처리:
        - 검정 배경 → 투명 처리 (black_threshold 이하 픽셀)
        - 전체 불투명도 조정
        저장 위치: temp/logo_heading_transparent.png
        """
        from PIL import Image
        img = Image.open(logo_path).convert("RGBA")
        px  = img.load()
        for y in range(img.height):
            for x in range(img.width):
                r, g, b, a = px[x, y]
                if r < black_threshold and g < black_threshold and b < black_threshold:
                    px[x, y] = (r, g, b, 0)            # 검정 → 투명
                else:
                    px[x, y] = (r, g, b, int(a * opacity))  # 불투명도 적용
        out = self.temp_dir / "logo_heading_transparent.png"
        img.save(str(out), "PNG")
        return out

    def get_duration(self, path: Path) -> float:
        """미디어 파일 길이(초) 반환"""
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", str(path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return 0.0
        return float(json.loads(result.stdout).get("format", {}).get("duration", 0))

    def _is_valid_audio(self, path: Path) -> bool:
        """
        ffprobe로 오디오 파일 유효성 검사
        - 파일 존재 + 1KB 이상
        - ffprobe가 duration을 정상적으로 읽을 수 있는지 확인
        """
        if not path.exists() or path.stat().st_size < 1024:
            log.warning(f"유효하지 않은 파일 (없거나 너무 작음): {path.name}")
            return False
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error",
                 "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1",
                 str(path)],
                capture_output=True,
                encoding="utf-8", errors="replace",
                timeout=5
            )
            if r.returncode != 0:
                log.warning(f"ffprobe 실패: {path.name}")
                return False
            return True
        except Exception as e:
            log.warning(f"유효성 검사 오류 ({path.name}): {e}")
            return False

    # ── Seamless 루프 처리 ────────────────────────────────────────────
    def _make_seamless_loop_file(self, sound_file: Path, cf_sec: float = 5.0) -> Path:
        """
        파일 끝→시작 경계에 acrossfade를 삽입한 seamless loop 파일 생성.
        stream_loop 적용 시 루프 경계가 자연스럽게 연결됨.

        원리:
          - 동일 파일 두 장 로드 → acrossfade(d=cf_sec)
          - 원본 길이(D)로 트리밍 → 끝 cf_sec 구간에 크로스페이드 내장
          - stream_loop 시: 파일 끝(A 앞부분 페이드인 완료) → 파일 시작(A 앞부분)
            → 연속적으로 들림
        """
        dur = self.get_duration(sound_file)
        if dur <= cf_sec * 2 + 1:
            log.debug(f"파일이 너무 짧아 크로스페이드 스킵 ({dur:.1f}s): {sound_file.name}")
            return sound_file

        output = self.temp_dir / f"seamless_{sound_file.stem}.mp3"
        cmd = [
            "ffmpeg", "-y",
            "-i", str(sound_file),
            "-i", str(sound_file),
            "-filter_complex",
            f"[0:a][1:a]acrossfade=d={cf_sec}:c1=tri:c2=tri",
            "-t", str(dur),   # 원본 길이로 트리밍 (끝 cf_sec에 크로스페이드 내장)
            "-b:a", "192k",
            str(output)
        ]
        if self._run(cmd, f"Seamless 루프 생성: {sound_file.name}"):
            return output

        log.warning(f"Seamless 루프 생성 실패 — 원본 사용: {sound_file.name}")
        return sound_file

    # ── 포인트 음원 침묵 패딩 ────────────────────────────────────────
    def _pad_short_sound_with_silence(self, sound_file: Path,
                                      min_total: float = 8.0,
                                      max_total: float = 15.0) -> Path:
        """
        짧은 포인트 사운드 뒤에 무작위 침묵 추가 → 반복 간격 자연스럽게 확보.
        예: 3초짜리 page turn + 9초 침묵 = 12초마다 1회 반복
        """
        import random
        dur = self.get_duration(sound_file)
        total = round(random.uniform(min_total, max_total), 1)
        pad_dur = max(1.0, total - dur)  # 최소 1초 침묵 보장

        output = self.temp_dir / f"padded_{sound_file.stem}.mp3"
        cmd = [
            "ffmpeg", "-y", "-i", str(sound_file),
            "-af", f"apad=pad_dur={pad_dur}",
            "-b:a", "192k", str(output)
        ]
        if self._run(cmd, f"침묵 패딩: {sound_file.name} ({dur:.1f}s → ~{total}s간격)"):
            return output
        log.warning(f"침묵 패딩 실패 — 원본 사용: {sound_file.name}")
        return sound_file

    # ── 오디오 믹싱 ──────────────────────────────────────────────────
    def mix_sounds(self, sound_files: list[Path], target_duration: int,
                   category: str = "") -> tuple | None:
        """
        여러 사운드 파일을 믹싱하고 목표 길이로 루프
        - 유효성 검사 후 통과한 파일로 최대 3개 레이어 구성
        - 레이어링: 최대 3개 사운드 동시 재생 (볼륨 조정)
        - 루프: 짧은 파일은 target_duration까지 반복
        - loudnorm 필터로 -18 LUFS 정규화 (ASMR/힐링 채널 기준)
        반환: (mixed_audio_path, actual_layers) 또는 None
        """
        # 믹싱 결과를 raw에 먼저 저장 후 LUFS 정규화
        raw_audio = self.temp_dir / "mixed_raw.mp3"
        output    = self.temp_dir / "mixed_audio.mp3"
        for f in [raw_audio, output]:
            if f.exists():
                f.unlink()

        # 유효성 검사 통과한 파일로 최대 3개 레이어 구성
        # duration 내림차순 정렬: 긴 파일(앰비언스) → 메인, 짧은 파일(효과음) → 포인트
        valid_files = []
        for f in sound_files:
            if self._is_valid_audio(f):
                valid_files.append(f)
            else:
                log.warning(f"사운드 건너뜀: {f.name}")

        # duration 기반 정렬 (ffprobe로 길이 확인)
        def get_duration(p: Path) -> float:
            try:
                import subprocess as sp
                r = sp.run(
                    ["ffprobe", "-v", "error", "-show_entries",
                     "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
                    capture_output=True, text=True, timeout=5
                )
                return float(r.stdout.strip())
            except Exception:
                return 0.0

        valid_files.sort(key=get_duration, reverse=True)
        layers = valid_files[:3]

        if not layers:
            log.error("유효한 사운드 파일이 없습니다")
            return None

        # ── library: 짧은 point 레이어에 침묵 간격 삽입 ──────────────
        # point 레이어 = 최단 파일(layers[2]). 30초 미만이면 패딩 적용
        # 결과: 8~15초 간격으로 자연스럽게 반복 (기존: 2~5초마다 반복)
        if category == "library" and len(layers) >= 3:
            point_dur = get_duration(layers[2])
            if point_dur < 30:
                log.info(f"Library point 레이어 침묵 패딩: {layers[2].name} ({point_dur:.1f}s)")
                layers[2] = self._pad_short_sound_with_silence(layers[2])

        # ── 루프 경계 크로스페이드 처리 ───────────────────────────────
        # 각 레이어를 seamless loop 파일로 변환 (끝→시작 연결 자연스럽게)
        seamless_layers = [self._make_seamless_loop_file(f) for f in layers]
        log.info(f"Seamless 처리 완료: {len(seamless_layers)}개 레이어")

        if len(seamless_layers) == 1:
            # 단일 사운드: seamless 루프
            cmd = [
                "ffmpeg", "-y",
                "-stream_loop", "-1",       # 무한 루프
                "-i", str(seamless_layers[0]),
                "-t", str(target_duration), # 목표 길이로 자름
                "-b:a", "192k",
                str(raw_audio)
            ]
        else:
            # 멀티 레이어 믹싱 (seamless 파일 사용)
            inputs = []
            for f in seamless_layers:
                inputs += ["-stream_loop", "-1", "-i", str(f)]

            # 각 레이어 볼륨 설정 (duration 내림차순 정렬 기반)
            # 메인(60~80%): 가장 긴 파일 = 앰비언스
            # 서브(10~30%): 중간 파일 = 배경 보완음
            # 포인트(5~15%): 가장 짧은 파일 = 효과음 (거의 안 들림)
            import random
            vol_ranges = [(0.60, 0.80), (0.10, 0.30), (0.05, 0.15)]
            volumes = [round(random.uniform(*r), 2) for r in vol_ranges[:len(seamless_layers)]]
            log.info(f"레이어 볼륨: {list(zip([f.name for f in layers], volumes))}")
            amix_inputs = "".join(f"[{i}:a]volume={volumes[i]}[a{i}];" for i in range(len(seamless_layers)))
            mix_inputs  = "".join(f"[a{i}]" for i in range(len(seamless_layers)))
            filter_complex = (
                f"{amix_inputs}"
                f"{mix_inputs}amix=inputs={len(seamless_layers)}:duration=longest"
            )

            cmd = [
                "ffmpeg", "-y",
                *inputs,
                "-filter_complex", filter_complex,
                "-t", str(target_duration),
                "-b:a", "192k",
                str(raw_audio)
            ]

        if not self._run(cmd, f"Mixing {len(layers)} sound layers → {target_duration//3600}h audio"):
            return None

        # -18 LUFS 정규화 + lowpass 8kHz (화이트노이즈/하이 프리퀀시 제거) + 마지막 5초 페이드아웃
        fade_start = max(0, target_duration - 5)
        cmd_lufs = [
            "ffmpeg", "-y",
            "-i", str(raw_audio),
            "-af", f"lowpass=f=8000,loudnorm=I=-18:TP=-2.0:LRA=11,afade=t=out:st={fade_start}:d=5",
            "-b:a", "192k",
            str(output)
        ]

        ok = self._run(cmd_lufs, "Normalizing audio → -18 LUFS")
        self._delete(raw_audio)

        if ok:
            log.info(f"Audio mixed: {output.name} ({output.stat().st_size // (1024*1024)}MB) @ -18 LUFS")
            log.info(f"실제 사용 레이어: {[f.name for f in layers]}")
            return output, layers
        return None

    # ── 영상 루프 ──────────────────────────────────────────────────────
    def prepare_video_loop(self, video_files: list[Path], target_duration: int) -> tuple | None:
        """
        영상 클립들을 이어붙이고 목표 길이로 루프
        - 1080p로 통일
        - 1080p 정규화 → concat 루프 → normalized 클립 즉시 삭제
        반환: (video_loop_path, actual_video_files) 또는 None
        """
        normalized_dir = self.temp_dir / "normalized"
        normalized_dir.mkdir(exist_ok=True)
        normalized = []    # 정규화된 temp 클립
        source_map = {}    # norm 파일 → 원본 파일 매핑

        # 1. 각 클립 1080p 정규화
        for i, vf in enumerate(video_files):
            out = normalized_dir / f"norm_{i:02d}.mp4"
            if not out.exists():
                cmd = [
                    "ffmpeg", "-y", "-i", str(vf),
                    "-vf", (
                        "scale=1920:1080:force_original_aspect_ratio=decrease,"
                        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1"
                    ),
                    #"-r", "30",
                    #"-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-r", "24",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "28",
                    "-an",  # 오디오 제거 (우리 사운드 따로 붙임)
                    str(out)
                ]
                if self._run(cmd, f"Normalizing clip {i+1}/{len(video_files)}"):
                    normalized.append(out)
                    source_map[out] = vf
            else:
                normalized.append(out)
                source_map[out] = vf

        if not normalized:
            return None

        # 2. target_duration을 채우는 데 필요한 최소 클립 집합 계산
        clip_durations = [(v, self.get_duration(v)) for v in normalized]
        accumulated = 0.0
        needed_clips = []
        for norm_clip, dur in clip_durations:
            needed_clips.append(norm_clip)
            accumulated += dur
            if accumulated >= target_duration:
                break
        # 전체 클립을 합쳐도 target_duration보다 짧으면 전부 사용 (루프로 채움)
        if accumulated < target_duration:
            needed_clips = normalized

        actual_videos = [source_map[c] for c in needed_clips]
        log.info(f"실제 사용 클립: {len(needed_clips)}/{len(normalized)}개 "
                 f"({min(accumulated, target_duration):.1f}s / {target_duration}s)")

        # 3. 클립들 이어붙이기
        concat_list = self.temp_dir / "concat_list.txt"
        total_clip_duration = sum(d for _, d in clip_durations if _ in needed_clips)
        repeat_times = max(1, int(target_duration / max(total_clip_duration, 1)) + 2)

        with open(concat_list, "w") as f:
            for _ in range(repeat_times):
                for v in needed_clips:
                    f.write(f"file '{v.resolve()}'\n")

        video_loop = self.temp_dir / "video_loop.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-t", str(target_duration),
            #"-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:v", "libx264", "-preset", "medium", "-crf", "28",
            "-movflags", "+faststart",
            "-an",
            str(video_loop)
        ]

        ok = self._run(cmd, f"Looping video to {target_duration//3600}h")

        # normalized 클립 즉시 삭제 (video_loop에 이미 합쳐짐)
        for f in normalized:
            self._delete(f)
        self._delete(concat_list)
        try:
            normalized_dir.rmdir()  # 빈 폴더 삭제
        except:
            pass

        if not ok:
            return None
        return video_loop, actual_videos

    # ── 로고 오버레이 ──────────────────────────────────────────────────
    def add_logo_overlay(self, video_path: Path, output_path: Path) -> Path:
        """
        영상 워터마크 삽입
        - 좌상단: logo_heading.png (가로형, 영상 너비의 17%, 불투명도 85%)
        - 우하단: logo.png (원형, 180px, 불투명도 60%)
        둘 다 없으면 원본 그대로 반환
        """
        has_heading = LOGO_HEADING_PATH.exists()
        has_circle  = LOGO_PATH.exists()

        if not has_heading and not has_circle:
            log.warning(f"로고 파일 없음 — 워터마크 스킵")
            return video_path

        inputs = ["-i", str(video_path)]
        filter_parts = []
        input_idx = 1

        if has_heading:
            # 좌상단: 영상 너비의 17%, 마진 12px, 불투명도 85%
            # 검정 배경 사전 제거: Pillow로 투명 PNG 생성 (geq 필터보다 훨씬 빠름)
            logo_h_png = self._prepare_logo_png(
                LOGO_HEADING_PATH, black_threshold=45, opacity=0.85
            )
            inputs += ["-i", str(logo_h_png)]
            filter_parts.append(
                f"[{input_idx}:v]scale=iw*0.17:-2,format=rgba[logo_h]"
            )
            filter_parts.append("[0:v][logo_h]overlay=12:12[v1]")
            input_idx += 1
            prev = "v1"
        else:
            prev = "0:v"

        if has_circle:
            inputs += ["-i", str(LOGO_PATH)]
            # 우하단: 180px, 불투명도 60%, 마진 20px
            filter_parts.append(
                f"[{input_idx}:v]scale=180:-2,"
                f"format=rgba,colorchannelmixer=aa=0.6[logo_c]"
            )
            filter_parts.append(f"[{prev}][logo_c]overlay=W-w-20:H-h-20[v2]")
            final_out = "v2"
        else:
            final_out = prev

        filter_complex = ";".join(filter_parts)

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", f"[{final_out}]",
            "-map", "0:a",
            #"-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:v", "libx264", "-preset", "medium", "-crf", "28",
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(output_path)
        ]

        if self._run(cmd, "Adding logo watermark to video"):
            log.info(f"Logo overlay done: {output_path.name}")
            return output_path
        else:
            log.warning("Logo overlay failed — returning video without logo")
            return video_path

    # ── 최종 merge ────────────────────────────────────────────────────
    def merge(self, video_loop: Path, audio: Path, output_path: Path) -> Path | None:
        has_logo = LOGO_HEADING_PATH.exists() or LOGO_PATH.exists()

        if has_logo:
            # 로고 있는 경우: 임시 merge → 로고 적용 → 임시 삭제
            temp_merged = self.temp_dir / "merged_no_logo.mp4"
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_loop),
                "-i", str(audio),
                "-c:v", "copy",  # 영상 재인코딩 없이 복사 (빠름)
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                "-movflags", "+faststart",  # 유튜브 업로드 최적화
                str(temp_merged)
            ]

            if not self._run(cmd, "Merging video + audio"):
                return None

            # video_loop, audio 사용 완료 → 즉시 삭제
            self._delete(video_loop, audio)

            # 로고 오버레이
            final = self.add_logo_overlay(temp_merged, output_path)

            # temp_merged 사용 완료 → 즉시 삭제
            if output_path.exists():
                self._delete(temp_merged)
        else:
            # 로고 없는 경우: 바로 최종 파일로 merge (temp 없음)
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_loop), "-i", str(audio),
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-shortest", "-movflags", "+faststart", str(output_path)
            ]
            if not self._run(cmd, "Merging video + audio → final"):
                return None
            self._delete(video_loop, audio)
            final = output_path

        if final and output_path.exists():
            size_mb = output_path.stat().st_size / (1024 * 1024)
            log.info(f"Final video: {output_path.name} ({size_mb:.0f}MB)")
        return final

    # ── 전체 파이프라인 ───────────────────────────────────────────────
    def produce(
        self,
        sound_files: list[Path],
        video_files: list[Path],
        duration_hours: int = 1,
        title: str = "output",
        category: str = "",
    ) -> tuple | None:  # (output_path, used_sounds, used_videos)
        """
        전체 영상 제작 파이프라인
        """
        target_duration = duration_hours * 3600
        log.info(f"Producing {duration_hours}h video...")

        # 1. 오디오 믹싱 (유효한 파일만 레이어로 사용)
        mix_result = self.mix_sounds(sound_files, target_duration, category=category)
        if not mix_result:
            return None
        audio, actual_sounds = mix_result  # 실제 사용된 레이어 추적

        # 2. 영상 루프 (실제 필요한 클립만 사용)
        loop_result = self.prepare_video_loop(video_files, target_duration)
        if not loop_result:
            self._delete(audio)
            return None
        video_loop, actual_videos = loop_result  # 실제 사용된 클립 추적

        # 3. 최종 합성
        safe_title = "".join(
            c for c in title[:40] if c.isalnum() or c in " _-"
        ).strip().replace(" ", "_")
        output_path = self.work_dir / f"{safe_title}_final.mp4"

        result = self.merge(video_loop, audio, output_path)

        # 파이프라인 완료 후 temp 폴더 전체 정리
        self.cleanup_temp()

        if result is None:
            return None
        # (최종영상경로, 실제사용사운드, 실제사용영상) 반환
        return result, actual_sounds, actual_videos

    def extract_shorts_clip(self, video_path: Path, duration: int = 58) -> Path | None:
        """
        풀영상 앞부분에서 쇼츠/릴스용 세로 클립 추출
        - duration: 클립 길이 (기본 58초, YouTube Shorts 60초 제한 여유)
        - 9:16 세로 비율로 크롭 (1080x1920)
        - 시작점: 3초 (인트로 어두운 부분 스킵)
        """
        if not video_path.exists():
            log.error(f"Shorts 추출 실패: 파일 없음 {video_path}")
            return None

        safe_name = video_path.stem.replace("_final", "")
        output_path = video_path.parent / f"{safe_name}_shorts.mp4"

        # 9:16 크롭: 원본 1920x1080 → 가운데 크롭 → 608x1080 → 스케일 1080x1920
        cmd = [
            "ffmpeg", "-y",
            "-ss", "3",                    # 3초부터 시작
            "-i", str(video_path),
            "-t", str(duration),           # 58초
            "-vf", (
                "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,"  # 9:16 크롭
                "scale=1080:1920"                      # 세로 HD
            ),
            "-c:v", "libx264", "-preset", "medium", "-crf", "28",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_path)
        ]

        if self._run(cmd, f"Extracting {duration}s Shorts clip"):
            size_mb = output_path.stat().st_size / (1024 * 1024)
            log.info(f"Shorts clip: {output_path.name} ({size_mb:.1f}MB)")
            return output_path
        else:
            log.error("Shorts 클립 추출 실패")
            return None