# Calmdromeda Automation Pipeline

> 힐링/ASMR 유튜브 채널 **Calmdromeda**의 영상 자동 생성 파이프라인

강박, 불안, 공황, 우울이 있는 사람들을 위한 치유 컨텐츠를 매일 자동으로 제작하고 업로드합니다.

---

## 주요 기능

- **AI 콘셉트 자동 생성** — Claude Haiku API로 매일 새로운 힐링 사운드 기획
- **소스 자동 수집** — Freesound(음원) + Pexels(영상) API로 CC0 라이선스 소스 수집
- **3레이어 사운드 믹싱** — 메인/서브/포인트 구조로 자연스러운 공간감 연출
- **영상 자동 제작** — FFmpeg로 1시간 풀영상 + YouTube Shorts 동시 제작
- **자동 업로드** — YouTube Data API로 매일 오후 8시 KST 예약 공개
- **완전 자동화** — GitHub Actions로 매일 무인 실행

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| Language | Python 3.10 |
| AI | Claude Haiku (Anthropic API) |
| 음원 | Freesound API (CC0/CC BY) |
| 영상 | Pexels API (무료) |
| 인코딩 | FFmpeg 7.1 |
| 업로드 | YouTube Data API v3 |
| 자동화 | GitHub Actions |
| 암호화 | AES-256-GCM |

---

## 설치

```bash
pip install -r requirements.txt
```

FFmpeg 설치 필요 — [ffmpeg.org](https://ffmpeg.org/download.html)

---

## 환경 변수

`.env.example`을 복사해서 `.env`를 만들고 API 키를 입력하세요.

```bash
cp .env.example .env
```

---

## 실행

```bash
# 자동 실행 (AI 기획 모드)
python pipeline.py

# 영상 재사용 + 사운드만 교체 (로컬 전용)
python pipeline.py --reuse-session 20260401_202159
```

---

## 채널

[@Calmdromeda](https://www.youtube.com/@Calmdromeda)