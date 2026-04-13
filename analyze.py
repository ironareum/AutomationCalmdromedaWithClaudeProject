"""
Calmdromeda YouTube 성과 분석 스크립트
2026.04.13 신규

[사용법]
  python analyze.py                # 최근 30일
  python analyze.py --days 60      # 최근 60일
  python analyze.py --days 7       # 최근 7일

[사전 준비]
  최초 실행 시 브라우저 인증 필요 (Analytics 스코프 추가)
  → credentials/analytics_token.json 자동 생성 (이후 자동 재사용)

[출력 항목]
  조회수 / 좋아요 / 평균 시청 지속시간 / 노출 클릭률(CTR) / 구독자 증가
  + 파이프라인 메타데이터 기반 카테고리 매핑
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

# ── 경로 설정 ─────────────────────────────────────────────────────────────
ROOT            = Path(__file__).parent
TOKEN_PATH      = ROOT / "credentials" / "analytics_token.json"
CLIENT_SECRET   = ROOT / "credentials" / "client_secret.json"
OUTPUT_DIR      = ROOT / "output"
USED_ASSETS     = ROOT / "used_assets.json"

# ── YouTube API 스코프 ────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


# ── 인증 ──────────────────────────────────────────────────────────────────

def get_credentials():
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("❌ Google API 라이브러리 없음. 설치:\n"
              "   pip install google-api-python-client google-auth-oauthlib google-auth-httplib2")
        sys.exit(1)

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET.exists():
                print(f"❌ client_secret.json 없음: {CLIENT_SECRET}")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    return creds


# ── YouTube 서비스 빌드 ───────────────────────────────────────────────────

def build_services(creds):
    from googleapiclient.discovery import build
    yt        = build("youtube",          "v3",  credentials=creds)
    yt_analyt = build("youtubeAnalytics", "v2",  credentials=creds)
    return yt, yt_analyt


# ── 채널 업로드 플레이리스트에서 영상 목록 수집 ──────────────────────────

def get_video_list(yt) -> list[dict]:
    """채널의 모든 업로드 영상 ID + 제목 + 게시일 반환"""
    # 채널 정보
    ch = yt.channels().list(part="contentDetails,snippet", mine=True).execute()
    channel_title = ch["items"][0]["snippet"]["title"]
    uploads_id    = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    print(f"📺 채널: {channel_title}")

    videos = []
    page_token = None
    while True:
        pl = yt.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_id,
            maxResults=50,
            pageToken=page_token,
        ).execute()

        for item in pl.get("items", []):
            videos.append({
                "video_id":    item["contentDetails"]["videoId"],
                "title":       item["snippet"]["title"],
                "published_at": item["snippet"]["publishedAt"][:10],
            })

        page_token = pl.get("nextPageToken")
        if not page_token:
            break

    # 영상 길이 가져오기 (Shorts 구분용, duration < 60s)
    # 50개씩 배치 처리
    for i in range(0, len(videos), 50):
        batch = videos[i:i+50]
        ids   = ",".join(v["video_id"] for v in batch)
        resp  = yt.videos().list(part="contentDetails", id=ids).execute()
        dur_map = {}
        for item in resp.get("items", []):
            dur_map[item["id"]] = _parse_duration(item["contentDetails"]["duration"])
        for v in batch:
            v["duration_sec"] = dur_map.get(v["video_id"], 0)
            v["is_shorts"]    = v["duration_sec"] <= 60

    return videos


def _parse_duration(iso: str) -> int:
    """PT1M30S → 90초"""
    import re
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m:
        return 0
    h, mn, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mn * 60 + s


# ── YouTube Analytics API로 지표 수집 ────────────────────────────────────

def get_analytics(yt_analyt, video_ids: list[str],
                  start_date: str, end_date: str) -> dict[str, dict]:
    """
    video_id → 지표 딕셔너리 반환
    지표: views, likes, estimatedMinutesWatched, averageViewDuration,
          impressionClickThroughRate, subscribersGained
    """
    if not video_ids:
        return {}

    # Analytics API는 한 번에 최대 200개 필터 가능
    results = {}
    for i in range(0, len(video_ids), 50):
        batch  = video_ids[i:i+50]
        filter_ = "video==" + ",".join(batch)
        try:
            resp = yt_analyt.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=end_date,
                metrics="views,likes,estimatedMinutesWatched,averageViewDuration,"
                        "impressionClickThroughRate,subscribersGained",
                dimensions="video",
                filters=filter_,
                sort="-views",
                maxResults=200,
            ).execute()
        except Exception as e:
            print(f"⚠️  Analytics API 오류: {e}")
            continue

        headers = [h["name"] for h in resp.get("columnHeaders", [])]
        for row in resp.get("rows", []):
            row_dict = dict(zip(headers, row))
            vid      = row_dict.get("video", "")
            results[vid] = {
                "views":      int(row_dict.get("views", 0)),
                "likes":      int(row_dict.get("likes", 0)),
                "watch_min":  round(float(row_dict.get("estimatedMinutesWatched", 0)), 1),
                "avg_sec":    int(row_dict.get("averageViewDuration", 0)),
                "ctr":        round(float(row_dict.get("impressionClickThroughRate", 0)) * 100, 1),
                "subs_gained":int(row_dict.get("subscribersGained", 0)),
            }

    return results


# ── 파이프라인 메타데이터에서 카테고리 매핑 ──────────────────────────────

def load_category_map() -> dict[str, str]:
    """video_id → category 매핑 (output/*/metadata.json 파싱)"""
    cat_map = {}
    if not OUTPUT_DIR.exists():
        return cat_map

    for meta_file in OUTPUT_DIR.glob("*/metadata.json"):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            # YouTube URL에서 video_id 추출
            yt_url = meta.get("youtube", {}).get("url", "")
            if "v=" in yt_url:
                vid = yt_url.split("v=")[-1].split("&")[0]
                cat_map[vid] = meta.get("category", "")
            # Shorts URL
            sh_url = meta.get("youtube_shorts", {}).get("url", "")
            if "v=" in sh_url:
                vid = sh_url.split("v=")[-1].split("&")[0]
                cat_map[vid] = meta.get("category", "") + " (Shorts)"
        except Exception:
            continue

    return cat_map


# ── 출력 ──────────────────────────────────────────────────────────────────

def _fmt_sec(sec: int) -> str:
    """90 → 1:30"""
    return f"{sec // 60}:{sec % 60:02d}"


def print_report(videos: list[dict], analytics: dict, cat_map: dict, days: int):
    # 지표 병합
    rows = []
    for v in videos:
        vid  = v["video_id"]
        stat = analytics.get(vid, {})
        if not stat:
            continue
        rows.append({
            **v,
            **stat,
            "category": cat_map.get(vid, "—"),
        })

    if not rows:
        print("⚠️  기간 내 조회 데이터 없음 (영상이 아직 없거나 조회수 0)")
        return

    # Shorts / 풀영상 분리
    shorts = [r for r in rows if r["is_shorts"]]
    fulls  = [r for r in rows if not r["is_shorts"]]

    def print_table(items: list[dict], label: str):
        if not items:
            return
        items = sorted(items, key=lambda x: x["views"], reverse=True)

        print(f"\n{'━'*72}")
        print(f"  {label}  (총 {len(items)}개)")
        print(f"{'━'*72}")
        print(f"{'#':>3}  {'카테고리':<14} {'제목':<30} {'조회수':>7} {'좋아요':>6} {'지속':>6}  {'CTR':>5}  {'구독+':>5}")
        print(f"{'─'*72}")

        total_views = 0
        total_ctr   = 0
        for i, r in enumerate(items, 1):
            title = r["title"][:28] + ".." if len(r["title"]) > 30 else r["title"]
            cat   = r["category"][:13]
            total_views += r["views"]
            total_ctr   += r["ctr"]
            print(
                f"{i:>3}  {cat:<14} {title:<30} "
                f"{r['views']:>7,}  {r['likes']:>5}  "
                f"{_fmt_sec(r['avg_sec']):>6}  "
                f"{r['ctr']:>4.1f}%  "
                f"{r['subs_gained']:>5}"
            )

        avg_views = total_views // len(items)
        avg_ctr   = round(total_ctr / len(items), 1)

        # 인사이트
        top       = items[0]
        top_watch = sorted(items, key=lambda x: x["avg_sec"], reverse=True)[0]
        top_ctr   = sorted(items, key=lambda x: x["ctr"],     reverse=True)[0]

        print(f"\n  📌 인사이트")
        print(f"  - 조회수 1위 : [{top['category']}] {top['title'][:40]} ({top['views']:,}회)")
        print(f"  - 시청지속 1위: [{top_watch['category']}] {top_watch['title'][:40]} ({_fmt_sec(top_watch['avg_sec'])})")
        print(f"  - CTR 1위    : [{top_ctr['category']}] {top_ctr['title'][:40]} ({top_ctr['ctr']}%)")
        print(f"  - 평균 조회수: {avg_views:,}회 | 평균 CTR: {avg_ctr}%")

    print(f"\n\n📊 Calmdromeda 영상 성과 분석 — 최근 {days}일")

    print_table(shorts, "🎬 Shorts")
    print_table(fulls,  "📹 풀영상")

    print(f"\n{'━'*72}\n")


# ── 메인 ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Calmdromeda YouTube 성과 분석")
    parser.add_argument("--days", type=int, default=30, help="분석 기간 (일, 기본값: 30)")
    args = parser.parse_args()

    end_date   = date.today().isoformat()
    start_date = (date.today() - timedelta(days=args.days)).isoformat()
    print(f"📅 분석 기간: {start_date} ~ {end_date} ({args.days}일)")

    print("🔐 YouTube 인증 중...")
    creds = get_credentials()
    yt, yt_analyt = build_services(creds)

    print("📋 영상 목록 수집 중...")
    videos = get_video_list(yt)
    print(f"   총 {len(videos)}개 영상 (Shorts {sum(1 for v in videos if v['is_shorts'])}개 포함)")

    video_ids = [v["video_id"] for v in videos]
    print("📈 Analytics 지표 수집 중...")
    analytics = get_analytics(yt_analyt, video_ids, start_date, end_date)

    print("🗂️  파이프라인 메타데이터 로드 중...")
    cat_map = load_category_map()

    print_report(videos, analytics, cat_map, args.days)


if __name__ == "__main__":
    main()
