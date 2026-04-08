"""
GitHub Actions 파이프라인 로그 추출기
- 기간 내 daily_pipeline.yml 실행 목록 조회
- 각 실행에서 아래 항목 추출 후 CSV 저장
  · 세션ID, sounds(실제사용), videos(실제사용)
  · title, shorts_title, mood, title_sub, subtitle_en
  · youtube_link, shorts_link
"""

import os
import re
import csv
import json
import zipfile
import io
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── 설정 ──────────────────────────────────────────────
GITHUB_TOKEN  = os.getenv("GITHUB_TOKEN")
OWNER         = "ironareum"
REPO          = "AutomationCalmdromedaWithClaudeProject"
WORKFLOW_FILE = "daily_pipeline.yml"
OUTPUT_CSV    = f"pipeline_log_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
# ──────────────────────────────────────────────────────

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
BASE = f"https://api.github.com/repos/{OWNER}/{REPO}"


def get_workflow_runs(start_date: str, end_date: str) -> list:
    """기간 내 workflow 실행 목록 반환. 날짜 형식: YYYY-MM-DD"""
    runs = []
    page = 1
    time_range = f"{start_date}T00:00:00Z..{end_date}T23:59:59Z"

    while True:
        url = f"{BASE}/actions/workflows/{WORKFLOW_FILE}/runs"
        params = {
            "created": time_range,
            "per_page": 100,
            "page": page,
            "status": "completed",
        }
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("workflow_runs", [])
        if not batch:
            break
        runs.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    print(f"[+] 총 {len(runs)}개 실행 조회됨 ({start_date} ~ {end_date})")
    return runs


def strip_gha_timestamp(line: str) -> str:
    """GitHub Actions 로그 줄 앞의 타임스탬프 제거
    예: '2026-04-08T06:05:13.1330000Z some text' -> 'some text'
    """
    return re.sub(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s?", "", line)


def get_run_log_text(run_id: int) -> str:
    """run_id의 로그 zip을 받아 타임스탬프 제거 후 텍스트로 합쳐 반환"""
    url = f"{BASE}/actions/runs/{run_id}/logs"
    resp = requests.get(url, headers=HEADERS, allow_redirects=True)

    if resp.status_code == 404:
        print(f"  [!] run {run_id}: 로그 없음 (만료 또는 실패)")
        return ""

    resp.raise_for_status()

    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            texts = []
            for name in sorted(zf.namelist()):
                if name.endswith(".txt"):
                    raw = zf.read(name).decode("utf-8", errors="replace")
                    # 각 줄의 GHA 타임스탬프 제거
                    cleaned = "\n".join(strip_gha_timestamp(l) for l in raw.splitlines())
                    texts.append(cleaned)
            return "\n".join(texts)
    except zipfile.BadZipFile:
        print(f"  [!] run {run_id}: zip 파싱 실패")
        return ""


def parse_log(log_text: str) -> dict:
    """로그에서 필요한 모든 필드 추출"""
    result = {
        "session_id":   "",
        "sounds":       "",
        "videos":       "",
        "title":        "",
        "shorts_title": "",
        "mood":         "",
        "title_sub":    "",
        "subtitle_en":  "",
        "youtube_link": "",
        "shorts_link":  "",
    }

    # ── 1. 세션ID: "=== Pipeline Start: 20260408_060513 ==="
    m = re.search(r"=== Pipeline Start:\s*(\d{8}_\d{6})", log_text)
    if m:
        result["session_id"] = m.group(1)

    # ── 2. 실제 사용 sounds / videos
    m2 = re.search(
        r"\[INFO\]\s*실제 사용:\s*sounds=\[([^\]]*)\],\s*videos=\[([^\]]*)\]",
        log_text
    )
    if m2:
        sounds = [s.strip().strip("'\"") for s in m2.group(1).split(",") if s.strip()]
        videos = [v.strip().strip("'\"") for v in m2.group(2).split(",") if v.strip()]
        result["sounds"] = " | ".join(sounds)
        result["videos"] = " | ".join(videos)

    # ── 3. Claude 응답 JSON 블록 파싱
    #    패턴: [INFO] Claude 응답:\n```json\n{...}\n```
    m3 = re.search(
        r"\[INFO\]\s*Claude 응답:\s*```json\s*(\{.*?\})\s*```",
        log_text,
        re.DOTALL
    )
    if m3:
        try:
            meta = json.loads(m3.group(1))
            result["title"]        = meta.get("title", "")
            result["shorts_title"] = meta.get("shorts_title", "")
            result["mood"]         = meta.get("mood", "")
            result["title_sub"]    = meta.get("title_sub", "")
            result["subtitle_en"]  = meta.get("subtitle_en", "")
        except json.JSONDecodeError:
            pass

    # ── 4. YouTube / Shorts 링크
    #    패턴: [INFO] YouTube : __https://...__ (공개: ...)
    yt = re.search(r"\[INFO\]\s*YouTube\s*:\s*__(\S+?)__", log_text)
    if yt:
        result["youtube_link"] = yt.group(1)

    sh = re.search(r"\[INFO\]\s*Shorts\s*:\s*__(\S+?)__", log_text)
    if sh:
        result["shorts_link"] = sh.group(1)

    return result


def main():
    if not GITHUB_TOKEN:
        print("[ERROR] .env 파일에 GITHUB_TOKEN이 없어요!")
        return

    print("=== GitHub Actions 로그 추출기 ===")

    def parse_date(prompt):
        while True:
            raw = input(prompt).strip()
            if len(raw) == 8 and raw.isdigit():
                return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
            print("  날짜 형식이 잘못됐어요. 8자리 숫자로 입력해주세요. 예: 20260408")

    start_date = parse_date("시작일자 (YYYYMMDD): ")
    end_date   = parse_date("종료일자 (YYYYMMDD): ")

    runs = get_workflow_runs(start_date, end_date)
    if not runs:
        print("조회된 실행이 없어요.")
        return

    rows = []
    for run in runs:
        run_id     = run["id"]
        run_number = run["run_number"]
        started_at = run.get("run_started_at", run.get("created_at", ""))[:19].replace("T", " ")
        conclusion = run.get("conclusion", "")

        print(f"  처리 중: run #{run_number} (id={run_id}, {started_at}, {conclusion})")

        log_text = get_run_log_text(run_id)
        parsed   = parse_log(log_text)

        rows.append({
            "run_number":   run_number,
            "run_id":       run_id,
            "started_at":   started_at,
            "conclusion":   conclusion,
            "session_id":   parsed["session_id"],
            "title":        parsed["title"],
            "shorts_title": parsed["shorts_title"],
            "mood":         parsed["mood"],
            "title_sub":    parsed["title_sub"],
            "subtitle_en":  parsed["subtitle_en"],
            "youtube_link": parsed["youtube_link"],
            "shorts_link":  parsed["shorts_link"],
            "sounds":       parsed["sounds"],
            "videos":       parsed["videos"],
        })

    fieldnames = [
        "run_number", "run_id", "started_at", "conclusion",
        "session_id", "title", "shorts_title", "mood",
        "title_sub", "subtitle_en", "youtube_link", "shorts_link",
        "sounds", "videos",
    ]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n[완료] {OUTPUT_CSV} 저장됨 ({len(rows)}행)")


if __name__ == "__main__":
    main()

# if __name__ == "__main__":
#     # ── 디버그용: 특정 run_id의 로그에서 YouTube 줄 찾기 ──
#     run_id = 24120543003  # run #23
#     log_text = get_run_log_text(run_id)
#     for line in log_text.splitlines():
#         if "YouTube" in line or "Shorts" in line:
#             print(repr(line))