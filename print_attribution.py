#!/usr/bin/env python3
"""
used_assets.json 기반 세션별 출처 블록 출력
YouTube 설명란 수기 업데이트용

사용법:
  python print_attribution.py                    # 전체 출력
  python print_attribution.py --quality good     # good만
  python print_attribution.py --session 20260329_101228  # 특정 세션
"""

import argparse
import json
from pathlib import Path

USED_ASSETS_FILE = Path(__file__).parent / "used_assets.json"


def extract_sound_id(filename: str) -> str | None:
    name = filename
    if name.startswith("intro_"):
        name = name[6:]
    part = name.split("_")[0]
    return part if part.isdigit() else None


def extract_video_id(filename: str) -> str | None:
    if filename.startswith("pexels_"):
        parts = filename.split("_")
        if len(parts) >= 2 and parts[1].isdigit():
            return parts[1]
    return None


def build_attribution(sounds: list, videos: list) -> str:
    lines = []

    sound_ids = []
    for name in (sounds or []):
        sid = extract_sound_id(name)
        if sid and sid not in sound_ids:
            sound_ids.append(sid)
    if sound_ids:
        lines.append("📻 Sound Sources (Freesound.org — CC0 / Attribution)")
        for i, sid in enumerate(sound_ids, 1):
            lines.append(f"Track {i}")
            lines.append(f"https://freesound.org/s/{sid}/")

    video_ids = []
    for name in (videos or []):
        vid = extract_video_id(name)
        if vid and vid not in video_ids:
            video_ids.append(vid)
    if video_ids:
        if lines:
            lines.append("")
        lines.append("🎬 Video Sources (Pexels.com — Free License)")
        for i, vid in enumerate(video_ids, 1):
            lines.append(f"Clip {i}")
            lines.append(f"https://www.pexels.com/video/{vid}/")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quality", choices=["good", "bad", "pending"], default=None)
    parser.add_argument("--session", default=None, help="특정 세션 ID")
    args = parser.parse_args()

    if not USED_ASSETS_FILE.exists():
        print(f"파일 없음: {USED_ASSETS_FILE}")
        return

    data = json.loads(USED_ASSETS_FILE.read_text(encoding="utf-8"))

    sessions = sorted(data.items())
    if args.session:
        sessions = [(k, v) for k, v in sessions if k == args.session]
    if args.quality:
        sessions = [(k, v) for k, v in sessions if v.get("quality") == args.quality]

    for session_id, info in sessions:
        quality = info.get("quality", "?")
        title = info.get("title", "")
        attribution = build_attribution(info.get("sounds", []), info.get("videos", []))

        print("=" * 60)
        print(f"[{session_id}] quality={quality}")
        print(f"제목: {title}")
        print("-" * 40)
        print(attribution)
        print()


if __name__ == "__main__":
    main()
