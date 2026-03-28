"""
FFmpeg Video Producer
2026.03.26 사운드 레이어링 + 영상 루프 합성 → 1~3시간 유튜브 영상 생성
2026.03.28 영상 우측 하단에 Calmdromeda 로고 워터마크 자동 삽입
"""

import subprocess
import logging
import json
from pathlib import Path

log = logging.getLogger(__name__)

# 로고 파일 경로 (프로젝트 루트 기준)
LOGO_PATH = Path(__file__).parent.parent / "assets" / "logo.png"


class VideoProducer:
    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self.temp_dir = work_dir / "temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._check_ffmpeg()

    def _check_ffmpeg(self):
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
            version = result.stdout.split("\n")[0]
            log.info(f"FFmpeg ready: {version[:50]}")
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

    def get_duration(self, path: Path) -> float:
        """미디어 파일 길이(초) 반환"""
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", str(path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return 0.0
        info = json.loads(result.stdout)
        return float(info.get("format", {}).get("duration", 0))

    def mix_sounds(self, sound_files: list[Path], target_duration: int) -> Path | None:
        """
        여러 사운드 파일을 믹싱하고 목표 길이로 루프
        - 레이어링: 최대 3개 사운드 동시 재생 (볼륨 조정)
        - 루프: 짧은 파일은 target_duration까지 반복
        """
        output = self.temp_dir / "mixed_audio.mp3"
        if output.exists():
            output.unlink()

        # 최대 3개 레이어만 사용
        layers = sound_files[:3]

        if len(layers) == 1:
            # 단일 사운드: 루프만
            cmd = [
                "ffmpeg", "-y",
                "-stream_loop", "-1",       # 무한 루프
                "-i", str(layers[0]),
                "-t", str(target_duration), # 목표 길이로 자름
                "-af", f"afade=t=out:st={target_duration - 5},d=5",  # 마지막 5초 페이드아웃?
                "-b:a", "192k",
                str(output)
            ]
        else:
            # 멀티 레이어 믹싱
            inputs = []
            for f in layers:
                inputs += ["-stream_loop", "-1", "-i", str(f)]

            # 각 레이어 볼륨 설정 (첫번째가 주 사운드, 나머지는 보조)
            volumes = [1.0, 0.6, 0.4]
            amix_inputs = "".join(f"[{i}:a]volume={volumes[i]}[a{i}];" for i in range(len(layers)))
            mix_inputs = "".join(f"[a{i}]" for i in range(len(layers)))
            filter_complex = (
                f"{amix_inputs}"
                f"{mix_inputs}amix=inputs={len(layers)}:duration=longest,"
                f"afade=t=out:st={target_duration - 5}:d=5"
            )

            cmd = [
                "ffmpeg", "-y",
                *inputs,
                "-filter_complex", filter_complex,
                "-t", str(target_duration),
                "-b:a", "192k",
                str(output)
            ]

        if self._run(cmd, f"Mixing {len(layers)} sound layers → {target_duration//3600}h audio"):
            log.info(f"Audio mixed: {output.name} ({output.stat().st_size // (1024*1024)}MB)")
            return output
        return None

    def prepare_video_loop(self, video_files: list[Path], target_duration: int) -> Path | None:
        """
        영상 클립들을 이어붙이고 목표 길이로 루프
        - 각 클립은 크로스페이드로 자연스럽게 전환
        - 1080p로 통일
        """
        normalized_dir = self.temp_dir / "normalized"
        normalized_dir.mkdir(exist_ok=True)
        normalized = []

        # 1. 각 영상 1080p로 정규화
        for i, vf in enumerate(video_files):
            out = normalized_dir / f"norm_{i:02d}.mp4"
            if not out.exists():
                cmd = [
                    "ffmpeg", "-y", "-i", str(vf),
                    "-vf", (
                        "scale=1920:1080:force_original_aspect_ratio=decrease,"
                        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1"
                    ),
                    "-r", "30",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-an",  # 오디오 제거 (우리 사운드 따로 붙임)
                    str(out)
                ]
                if self._run(cmd, f"Normalizing clip {i+1}/{len(video_files)}"):
                    normalized.append(out)
            else:
                normalized.append(out)

        if not normalized:
            return None

        # 2. 클립들 이어붙이기
        concat_list = self.temp_dir / "concat_list.txt"
        # target_duration을 채울 때까지 반복
        total_clip_duration = sum(self.get_duration(v) for v in normalized)
        repeat_times = max(1, int(target_duration / max(total_clip_duration, 1)) + 2)

        with open(concat_list, "w") as f:
            for _ in range(repeat_times):
                for v in normalized:
                    f.write(f"file '{v.resolve()}'\n")

        video_loop = self.temp_dir / "video_loop.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-t", str(target_duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-movflags", "+faststart",
            "-an",
            str(video_loop)
        ]

        if self._run(cmd, f"Looping video to {target_duration//3600}h"):
            return video_loop
        return None

    def add_logo_overlay(self, video_path: Path, output_path: Path) -> Path | None:
        """
        영상 우측 하단에 반투명 로고 워터마크 삽입
        로고 없으면 그냥 원본 반환
        """
        if not LOGO_PATH.exists():
            log.warning(f"Logo not found at {LOGO_PATH} ? skipping overlay")
            return video_path

        # 로고: 우측 하단, 너비 180px, 불투명도 60%
        filter_complex = (
            "[1:v]scale=180:-1,format=rgba,"
            "colorchannelmixer=aa=0.6[logo];"
            "[0:v][logo]overlay=W-w-30:H-h-30"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(LOGO_PATH),
            "-filter_complex", filter_complex,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(output_path)
        ]

        if self._run(cmd, "Adding logo watermark to video"):
            log.info(f"Logo overlay done: {output_path.name}")
            return output_path
        else:
            log.warning("Logo overlay failed ? returning video without logo")
            return video_path

    def merge(self, video_loop: Path, audio: Path, output_path: Path) -> Path | None:
        # 임시 merge 파일 (로고 입히기 전)
        temp_merged = self.temp_dir / "merged_no_logo.mp4"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_loop),
            "-i", str(audio),
            "-c:v", "copy",         # 영상 재인코딩 없이 복사 (빠름)
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",  # 유튜브 업로드 최적화
            str(temp_merged)
        ]

        if not self._run(cmd, "Merging video + audio"):
            return None

        # 로고 오버레이
        final = self.add_logo_overlay(temp_merged, output_path)
        if final:
            size_mb = output_path.stat().st_size / (1024 * 1024) if output_path.exists() else 0
            log.info(f"Final video: {output_path.name} ({size_mb:.0f}MB)")
        return final

    def produce(
        self,
        sound_files: list[Path],
        video_files: list[Path],
        duration_hours: int = 3,
        title: str = "output"
    ) -> Path | None:
        """
        전체 영상 제작 파이프라인
        """
        target_duration = duration_hours * 3600
        log.info(f"Producing {duration_hours}h video...")

        # 1. 오디오 믹싱
        audio = self.mix_sounds(sound_files, target_duration)
        if not audio:
            return None

        # 2. 영상 루프
        video_loop = self.prepare_video_loop(video_files, target_duration)
        if not video_loop:
            return None

        # 3. 최종 합성
        safe_title = "".join(
            c for c in title[:40] if c.isalnum() or c in " _-"
        ).strip().replace(" ", "_")
        output_path = self.work_dir / f"{safe_title}_final.mp4"

        return self.merge(video_loop, audio, output_path)
