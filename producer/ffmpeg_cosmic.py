"""
Cosmic Pipeline FFmpeg Producer
2026.06.29 자연소리 파이프라인(ffmpeg_producer.py)으로부터 분리

[설계 원칙]
  - 기존 ffmpeg_producer.py (자연소리 파이프라인) 절대 수정 금지
  - Jamendo 음악 특성: 이미 마스터링된 음원 → loudnorm 적용 시 왜곡 발생
  - 볼륨 부스트 전략: LUFS 측정 후 단순 volume 필터만 사용 (왜곡 없음)
  - 영상 루프: stream_loop -1 PTS 불연속 문제 → loop 필터 (frame-based) 사용
"""

import logging
import re
import subprocess
from pathlib import Path

from producer.ffmpeg_producer import VideoProducer

log = logging.getLogger(__name__)


class CosmicProducer(VideoProducer):
    """
    코스믹 파이프라인 전용 프로듀서.
    VideoProducer를 상속하되 오디오·루프 처리만 오버라이드.
    자연소리 파이프라인(VideoProducer)은 수정하지 않는다.
    """

    def _get_frame_count(self, video_path: Path) -> int | None:
        """
        ffprobe로 영상 총 프레임 수 반환.
        loop 필터의 size 파라미터 (loop=-1:size=N:start=0) 에 사용.
        nb_frames 없으면 count_packets fallback.
        """
        try:
            r = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=nb_frames",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(video_path),
                ],
                capture_output=True, text=True, timeout=15,
            )
            val = r.stdout.strip()
            if val.isdigit():
                log.info(f"프레임 수 (nb_frames): {val} — {video_path.name}")
                return int(val)
        except Exception as e:
            log.warning(f"nb_frames 조회 실패 ({video_path.name}): {e}")

        # nb_frames 컨테이너에 없는 경우 packet count fallback (느리지만 신뢰성 높음)
        try:
            r2 = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-select_streams", "v:0",
                    "-count_packets",
                    "-show_entries", "stream=nb_read_packets",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(video_path),
                ],
                capture_output=True, text=True, timeout=60,
            )
            val2 = r2.stdout.strip()
            if val2.isdigit():
                log.info(f"프레임 수 (count_packets): {val2} — {video_path.name}")
                return int(val2)
        except Exception as e:
            log.warning(f"count_packets fallback 실패 ({video_path.name}): {e}")

        return None

    def _detect_leading_silence(
        self,
        audio_path: Path,
        threshold_db: float = -45,
        min_silence: float = 1.0,
        max_trim: float = 20.0,
    ) -> float:
        """
        오디오 시작 부분 무음 길이 측정 (silencedetect).
        0초부터 시작하는 무음 구간만 감지 — 곡 중간 무음은 건드리지 않음.
        무음 없거나 측정 실패 시 0.0 반환 (트리밍 스킵, 기존 동작 유지).
        """
        try:
            r = subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-nostats",
                    "-i", str(audio_path),
                    "-af", f"silencedetect=noise={threshold_db}dB:d={min_silence}",
                    "-f", "null", "-",
                ],
                capture_output=True, text=True, timeout=30,
            )
        except Exception as e:
            log.warning(f"무음 감지 실패 ({audio_path.name}): {e}")
            return 0.0

        if not re.search(r"silence_start:\s*0(?:\.0+)?\b", r.stderr):
            return 0.0
        m = re.search(r"silence_end:\s*([\d.]+)", r.stderr)
        if not m:
            return 0.0

        dur = min(float(m.group(1)), max_trim)
        log.info(f"시작 무음 {dur:.1f}s 감지 — {audio_path.name}")
        return dur

    def mix_sounds_music(
        self,
        sound_files: list[Path],
        target_duration: int,
    ) -> tuple | None:
        """
        Jamendo 음악 전용 오디오 믹싱.
        loudnorm 없이 볼륨 부스트만 적용 (왜곡 방지).

        볼륨 정책:
          ≥ -20 LUFS : 그대로 (충분)
          -20 ~ -24  : volume=1.5 (약 +3.5dB)
          < -24      : volume=2.0 (+6dB)

        반환: (audio_path, [music_file], measured_lufs, source_lufs, {}) | None
        """
        output = self.temp_dir / "mixed_music.mp3"
        if output.exists():
            output.unlink()

        valid = [f for f in sound_files if self._is_valid_audio(f)]
        if not valid:
            log.error("유효한 음악 파일 없음")
            return None

        # 음악은 단일 트랙 (가장 앞에 있는 것 = 가장 긴 것)
        music_file = valid[0]
        audio_source = music_file  # 실제 루프/믹싱에 쓰이는 소스 (트리밍 시 교체됨)

        # 시작 무음 트리밍 — 루프 걸기 전에 한 번만 잘라내서 루프 반복마다 무음이
        # 재발하는 것을 방지 (stream_loop는 루프마다 파일 진짜 처음으로 되돌아감)
        leading_silence = self._detect_leading_silence(music_file)
        if leading_silence > 0:
            trimmed = self.temp_dir / f"trimmed_{music_file.name}"
            if self._run([
                "ffmpeg", "-y",
                "-ss", str(leading_silence),
                "-i", str(music_file),
                "-c", "copy",
                str(trimmed),
            ], f"시작 무음 {leading_silence:.1f}s 트리밍"):
                audio_source = trimmed
            else:
                log.warning("무음 트리밍 실패 — 원본 트랙 그대로 사용")

        # LUFS 측정 (첫 60초 샘플링) — 원본 파일명으로 기록 (크레딧/메타데이터용)
        measured_lufs = self._measure_lufs(audio_source)
        source_lufs: dict[str, float | None] = {music_file.name: measured_lufs}
        log.info(f"음악 소스 LUFS: {measured_lufs} dB — {music_file.name}")

        # 볼륨 부스트 결정
        if measured_lufs is None or measured_lufs >= -20:
            vol = 1.0
            label = f"볼륨 그대로 ({measured_lufs} LUFS)"
        elif measured_lufs >= -24:
            vol = 1.5
            label = f"volume=1.5 ({measured_lufs:.1f} → ~{measured_lufs + 3.5:.1f} LUFS 추정)"
        else:
            vol = 2.0
            label = f"volume=2.0 ({measured_lufs:.1f} → ~{measured_lufs + 6:.1f} LUFS 추정)"

        log.info(f"오디오 볼륨 조정: {label}")

        fade_start = max(0, target_duration - 5)
        af = f"volume={vol},highpass=f=80,afade=t=out:st={fade_start}:d=5"

        dur_label = f"{target_duration // 3600}h" if target_duration >= 3600 else f"{target_duration // 60}min"
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", str(audio_source),
            "-t", str(target_duration),
            "-af", af,
            "-b:a", "192k",
            str(output),
        ]

        if not self._run(cmd, f"음악 믹스 ({dur_label}, vol={vol})"):
            return None

        size_mb = output.stat().st_size / (1024 * 1024)
        log.info(f"음악 믹스 완료: {output.name} ({size_mb:.1f}MB)")
        return output, [music_file], measured_lufs, source_lufs, {}
