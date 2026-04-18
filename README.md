# Calmdromeda Automation Pipeline

> 힐링/ASMR 유튜브 채널 **Calmdromeda**의 영상 자동 생성 파이프라인

강박, 불안, 공황, 우울이 있는 사람들을 위한 치유 컨텐츠를 매일 자동으로 제작하고 업로드합니다.

---

## 주요 기능

- **AI 콘셉트 자동 생성** — Claude Haiku API로 매일 새로운 힐링 사운드 기획 (17개 카테고리 로테이션)
- **소스 자동 수집** — Freesound(음원) + Pexels(영상) API로 CC0/CC BY 라이선스 소스 수집
- **3레이어 사운드 믹싱** — 메인/서브/포인트 구조로 자연스러운 공간감 연출, -18 LUFS 정규화
- **영상 자동 제작** — FFmpeg로 1~3시간 풀영상 + YouTube Shorts(40초) 동시 제작
- **썸네일 자동 생성** — 영상 첫 프레임 기반 색상 추출 + 한/영 타이포그래피 자동 합성
- **자동 업로드** — YouTube Data API로 다음날 오후 6시 30분 KST 예약 공개
- **Instagram Reels 배포** — Meta Graph API로 Reels 자동 업로드
- **암호화 데이터 관리** — AES-256-GCM으로 사용 이력 암호화 후 별도 브랜치(`data`)에 보관
- **완전 자동화** — GitHub Actions로 매일 오전 9시 UTC (오후 6시 KST) 무인 실행

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| Language | Python 3.10+ |
| AI | Claude Haiku (Anthropic API) |
| 음원 | Freesound API (CC0/CC BY) |
| 영상 | Pexels API (무료 4K) |
| 인코딩 | FFmpeg 7.1 |
| 업로드 | YouTube Data API v3 |
| SNS | Instagram Graph API v25 |
| 백업 | Google Drive (rclone) |
| 자동화 | GitHub Actions |
| 암호화 | AES-256-GCM |

---

## 프로젝트 구조

```
AutomationCalmdromedaWithClaudeProject/
│
├── pipeline.py                 # 메인 진입점 — 전체 파이프라인 오케스트레이션
├── config.py                   # 환경변수, 경로, 카테고리 매핑 설정
├── crypto_utils.py             # AES-256-GCM 암복호화 유틸리티
├── analyze.py                  # 파이프라인 결과 분석/리포팅
├── extract_pipeline_logs.py    # 실행 로그 추출 유틸리티
├── make_thumbnail.py           # 썸네일 단독 생성 스크립트
├── test_mix.py                 # 오디오 믹싱 단독 테스트
├── blacklist.json              # 저품질 음원 파일 블랙리스트
├── requirements.txt
│
├── .github/workflows/
│   └── daily_pipeline.yml      # GitHub Actions 스케줄 워크플로우 (6시간 타임아웃)
│
├── planner/
│   └── concept_generator.py    # Claude Haiku → 일일 콘셉트 생성
│
├── collector/
│   ├── freesound.py            # Freesound API 음원 수집 (3레이어)
│   └── pexels.py               # Pexels API 영상 수집 (5클립)
│
├── producer/
│   ├── ffmpeg_producer.py      # FFmpeg 영상/오디오 인코딩 + 로고 합성
│   └── thumbnail.py            # YouTube 썸네일 생성 (1280×720)
│
├── uploader/
│   ├── youtube.py              # YouTube 업로드 + 예약 공개
│   └── instagram.py            # Instagram Reels 업로드
│
├── tests/
│   └── test_pipeline.py        # 54개 자동화 테스트
│
└── assets/
    ├── fonts/
    │   ├── RIDIBatang.otf      # 한국어 썸네일 폰트
    │   ├── Bitter-Bold.ttf
    │   └── Bitter-Italic.ttf   # 영어 썸네일 폰트
    ├── logo_heading.png        # 좌상단 브랜드 로고
    ├── logo.png                # 우하단 원형 배지
    └── sounds/                 # 로컬 폴백 음원 (gitignored)
```

**실행 결과물 (output/, gitignored):**
```
output/{session_id}/
├── videos/         # Pexels에서 받은 원본 영상 클립
├── audio/          # 믹싱 중간 결과물 (임시)
├── final.mp4       # 최종 풀영상 (1~3시간)
├── shorts.mp4      # YouTube Shorts용 40초 클립
├── thumbnails/     # 생성된 썸네일 PNG
├── metadata.json   # 세션 전체 메타데이터
├── pipeline.log    # 실행 로그
└── temp/           # FFmpeg 임시 파일 (자동 삭제)
```

---

## 파이프라인 흐름도

```
┌─────────────────────────────────────────────────────────────┐
│                      GitHub Actions (매일 09:00 UTC)         │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
              │  data 브랜치 복호화      │
              │  used_assets.json.enc   │
              │  history.txt.enc        │
              └────────────┬────────────┘
                           │
                           ▼
            ┌──────────────────────────────┐
            │  [Planner] 콘셉트 생성        │
            │  concept_generator.py         │
            │  · Claude Haiku API 호출      │
            │  · 카테고리 로테이션 선택      │
            │  · 제목/태그/쿼리/설명 생성   │
            └──────────────┬───────────────┘
                           │  concept JSON
                ┌──────────┴──────────┐
                │                     │
                ▼                     ▼
  ┌─────────────────────┐  ┌─────────────────────┐
  │  [Collector] 음원    │  │  [Collector] 영상    │
  │  freesound.py        │  │  pexels.py           │
  │  · Main 레이어       │  │  · 5개 클립 수집     │
  │  · Sub 레이어        │  │  · 사람 필터링       │
  │  · Point 레이어      │  │  · 중복 방지         │
  │  · 중복/블랙리스트   │  │  · 최장 순 정렬      │
  │    체크              │  └──────────┬──────────┘
  └──────────┬──────────┘             │
             │  audio files           │  video clips
             └──────────┬────────────┘
                        │
                        ▼
          ┌─────────────────────────────┐
          │  [Producer] 영상 제작        │
          │  ffmpeg_producer.py          │
          │  · 3레이어 오디오 믹싱       │
          │  · -18 LUFS 정규화          │
          │  · 영상 루프 + 크로스페이드  │
          │  · 로고 워터마크 합성        │
          │  · 최종 인코딩 (CRF 28)     │
          └──────────────┬──────────────┘
                         │  final.mp4
                ┌────────┴────────┐
                │                 │
                ▼                 ▼
  ┌─────────────────────┐  ┌─────────────────────┐
  │  [Producer] 썸네일   │  │  [Producer] Shorts   │
  │  thumbnail.py        │  │  ffmpeg_producer.py  │
  │  · 첫 프레임 추출    │  │  · 앞 40초 클립      │
  │  · 색상 자동 추출    │  │  · shorts.mp4 생성   │
  │  · 한/영 타이포      │  └──────────┬──────────┘
  │  · 로고 합성         │             │
  └──────────┬──────────┘             │
             │                        │
             └────────────┬───────────┘
                          │
                          ▼
          ┌───────────────────────────────┐
          │  [Uploader] 배포               │
          │                               │
          │  youtube.py                   │
          │  · 풀영상 예약 업로드          │
          │    (다음날 18:30 KST)          │
          │  · Shorts 업로드              │
          │                               │
          │  instagram.py                 │
          │  · Reels 업로드               │
          └───────────────┬───────────────┘
                          │
                          ▼
          ┌───────────────────────────────┐
          │  [Backup & Cleanup]           │
          │  · Google Drive rclone 백업   │
          │  · used_assets.json 업데이트  │
          │  · AES-256 암호화             │
          │  · data 브랜치에 커밋/푸시    │
          └───────────────────────────────┘
```

---

## 설치

```bash
pip install -r requirements.txt
```

FFmpeg 설치 필요 — [ffmpeg.org](https://ffmpeg.org/download.html)

---

## 실행

```bash
# 자동 실행 — AI가 카테고리 선택 후 전체 파이프라인 수행
python pipeline.py

# 카테고리 지정 실행 (로컬 전용, 업로드 없음)
python pipeline.py --category rain

# 영상 재사용 — 기존 세션의 영상은 그대로, 사운드/메타데이터만 새로 생성
python pipeline.py --reuse-session 20260401_202159

# 암호화 키 생성 (최초 1회)
python crypto_utils.py --generate-key
```

---

## 테스트

총 **9개 테스트 스위트, 54개 케이스**로 파이프라인 핵심 로직을 검증합니다.  
GitHub Actions에서 파이프라인 실행 전 자동으로 수행됩니다.

### 실행 방법

```bash
# 전체 테스트
pytest tests/test_pipeline.py -v

# 특정 스위트만 실행
pytest tests/test_pipeline.py -v -k "Preflight"
pytest tests/test_pipeline.py -v -k "Category"
pytest tests/test_pipeline.py -v -k "Thumbnail"

# 빠른 확인 (결과 요약만)
pytest tests/test_pipeline.py
```

### 테스트 스위트 구성

| 스위트 | 케이스 수 | 검증 내용 |
|--------|-----------|-----------|
| `TestPreflightChecks` | 10 | FFmpeg 설치, 환경변수, API 키, JSON 유효성 |
| `TestPickCategory` | 6 | 카테고리 로테이션, 중복 제외 보장 |
| `TestGetRecentCategories` | 4 | 최근 사용 카테고리 추출 |
| `TestBlacklist` | 4 | 블랙리스트 로드 및 필터링 |
| `TestRegisterUsedSession` | 3 | 세션 이력 등록 (`used_assets.json`) |
| `TestGenerateDescription` | 11 | 한/영 설명문 생성 |
| `TestPexelsGetBestFile` | 7 | 영상 파일 선택 및 정렬 |
| `TestPexelsPeopleFilter` | 2 | 사람 등장 영상 필터링 |
| `TestThumbnailUtils` | 5 | 폰트 로드, 색상 추출, 크기 계산 |

---

## 채널

[@Calmdromeda](https://www.youtube.com/@Calmdromeda)
