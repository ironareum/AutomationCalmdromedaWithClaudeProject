# Calmdromeda Automation Pipeline

> 힐링/명상 유튜브 채널 **Calmdromeda**의 영상 자동 생성 파이프라인

강박, 불안, 공황, 우울이 있는 사람들을 위한 치유 컨텐츠를 매주 자동으로 제작하고 업로드합니다.

---

## 파이프라인 종류

| 파이프라인 | 실행 요일 | 영상 길이 | 음원 소스 | 숏폼 |
|-----------|---------|---------|---------|------|
| **자연소리** (`pipeline.py`) | 화·토 | 1~3시간 | Freesound (3레이어) | 1개 (D+1) |
| **만다라/프랙탈** (`pipeline_mandala.py`) | 수·일 | 1시간 | Jamendo (CC) | 2개 (D+1·D+2) |
| **자연 숏폼** (`shorts_pipeline.py`) | 금 | — | Freesound | 1개 (D+1 토요일) |

### 주간 업로드 스케줄

| 요일 | 업로드 내용 |
|------|-----------|
| 월 | 만다라 롱폼 19:30 + 만다라 숏폼1 18:30 |
| 화 | 만다라 숏폼2 18:30 |
| 수 | 자연 롱폼 19:30 + 자연 숏폼 18:30 |
| 목 | 만다라 롱폼 19:30 + 만다라 숏폼1 18:30 |
| 금 | 만다라 숏폼2 18:30 |
| 토 | 자연 숏폼 18:30 |
| 일 | 자연 롱폼 19:30 + 자연 숏폼 18:30 |

---

## 주요 기능

- **AI 콘셉트 자동 생성** — Claude Haiku로 제목·태그·설명·썸네일 문구 일괄 생성
- **자연소리 수집** — Freesound API (CC0/CC BY), 메인/서브/포인트 3레이어 믹싱, -18 LUFS 정규화
- **만다라 음원 수집** — Jamendo API (CC), genres·vartags 기반 필터링, 재사용 자동 스킵
- **영상 수집** — Pexels API (4K), 카테고리별 쿼리, 사람 필터링
- **2-Pass FFmpeg 인코딩** — 정규화 → 루프+로고 (Pass 1) → 오디오 머지 (Pass 2, stream copy)
- **썸네일 자동 생성** — 첫 프레임 색상 추출 + 한/영 타이포그래피 합성 (1280×720)
- **분산 업로드 예약** — `days_ahead` 파라미터로 D+1·D+2 날짜별 YouTube 예약 공개
- **설명란 자동 구성** — 한글 설명 → 영문 설명 → Jamendo 출처 (아티스트·CC 라이선스)
- **재사용 방지** — `used_assets.json`으로 음원·영상 중복 사용 차단
- **암호화 데이터 관리** — AES-256-GCM으로 사용 이력 암호화 후 `data` 브랜치에 보관

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| Language | Python 3.11+ |
| AI | Claude Haiku 4.5 (Anthropic API) |
| 자연 음원 | Freesound API (CC0/CC BY) |
| 만다라 음원 | Jamendo API (CC BY) |
| 영상 | Pexels API (무료 4K) |
| 인코딩 | FFmpeg |
| 업로드 | YouTube Data API v3 |
| 백업 | Google Drive (rclone) |
| 자동화 | GitHub Actions |
| 암호화 | AES-256-GCM |

---

## 프로젝트 구조

```
AutomationCalmdromedaWithClaudeProject/
│
├── pipeline.py                 # 자연소리 롱폼 파이프라인
├── pipeline_mandala.py         # 만다라/프랙탈 롱폼 + 숏폼 파이프라인
├── shorts_pipeline.py          # 자연소리 숏폼 전용 파이프라인
├── config.py                   # 환경변수, 경로, 카테고리 설정
├── crypto_utils.py             # AES-256-GCM 암복호화 유틸리티
├── test_jamendo.py             # Jamendo API 단독 테스트 스크립트
├── blacklist.json              # 저품질 음원 블랙리스트
├── requirements.txt
│
├── .github/workflows/
│   ├── daily_pipeline.yml      # 자연소리 롱폼 (화·토 UTC 00:00)
│   ├── mandala_pipeline.yml    # 만다라 롱폼 (수·일 UTC 00:00)
│   └── daily_shorts.yml        # 자연 숏폼 (금 UTC 00:00 → 토요일 업로드)
│
├── planner/
│   ├── concept_generator.py    # 자연소리 콘셉트 생성 (12개 카테고리)
│   └── mandala_concept.py      # 만다라 콘셉트 생성 (3개 카테고리)
│
├── collector/
│   ├── freesound.py            # Freesound API 음원 수집 + used_assets 관리
│   ├── jamendo.py              # Jamendo API 음원 수집 + track id 재사용 방지
│   └── pexels.py               # Pexels API 영상 수집
│
├── producer/
│   ├── ffmpeg_producer.py      # FFmpeg 인코딩, 로고 합성, 숏폼 추출
│   └── thumbnail.py            # YouTube 썸네일 생성 (1280×720)
│
├── uploader/
│   ├── youtube.py              # YouTube 업로드 + days_ahead 예약 공개
│   └── instagram.py            # Instagram Reels 업로드
│
└── assets/
    ├── fonts/
    │   ├── RIDIBatang.otf
    │   ├── Bitter-Bold.ttf
    │   └── Bitter-Italic.ttf
    ├── logo_heading.png
    └── logo.png
```

---

## 파이프라인 흐름도

### 자연소리 롱폼 (`pipeline.py`)

```
GitHub Actions (화·토 09:00 KST)
        │
        ▼
  data 브랜치 복호화 (used_assets.json.enc)
        │
        ▼
  [Planner] concept_generator.py
  · Claude Haiku → 콘셉트 생성
  · 12개 카테고리 로테이션
        │
   ┌────┴────┐
   ▼         ▼
[음원]     [영상]
freesound  pexels.py
3레이어     4K 클립
   │         │
   └────┬────┘
        ▼
  [Producer] ffmpeg_producer.py
  · 3레이어 믹싱, -18 LUFS
  · 영상 루프 + 로고
  · 숏폼 추출 (D+1 18:30)
        │
   ┌────┴────┐
   ▼         ▼
[썸네일]  [YouTube 업로드]
           롱폼 D+1 19:30
           숏폼 D+1 18:30
        │
        ▼
  used_assets.json 암호화 → data 브랜치 저장
```

### 만다라/프랙탈 롱폼 (`pipeline_mandala.py`)

```
GitHub Actions (수·일 09:00 KST)
        │
        ▼
  data 브랜치 복호화
        │
        ▼
  [Planner] mandala_concept.py
  · Claude Haiku → 제목/설명/태그 생성
  · 3개 카테고리: mandala / fractal / cosmic_meditation
  · 제목 고정 포맷: 명상음악 | {감성문구} | Meditation Music - {SEO키워드}
        │
   ┌────┴────┐
   ▼         ▼
[음원]     [영상]
jamendo.py pexels.py
ambient/   만다라·우주
newage     비주얼
genres 기반
2회 API 호출
vartags 필터
   │         │
   └────┬────┘
        ▼
  [Producer] ffmpeg_producer.py
  · 2-Pass 인코딩 (정규화 → 루프+로고 → 머지)
  · 숏폼1: 1/3 지점(20분) → D+1 18:30
  · 숏폼2: 2/3 지점(40분) → D+2 18:30
        │
   ┌────┴────┐
   ▼         ▼
[썸네일]  [YouTube 업로드]
           롱폼 D+1 19:30
           숏폼1 D+1 18:30
           숏폼2 D+2 18:30
        │
        ▼
  metadata.json 저장 (jamendo_track 출처 포함)
  used_assets.json 암호화 → data 브랜치 저장
```

---

## 카테고리

### 자연소리 (12개)
| 카테고리 | 설명 |
|---------|------|
| `rain` | 빗소리 (창문, 숲, 도심) |
| `rain_thunder` | 천둥번개 빗소리 |
| `ocean` | 파도·해변 |
| `forest` | 숲속 자연음 |
| `birds` | 새소리·새벽 숲 |
| `white_noise` | 화이트노이즈 계열 |
| `camping` | 캠프파이어·텐트 |
| `underwater` | 수중·수족관 |
| `summer_night` | 여름밤·귀뚜라미 |
| `winter_snow` | 눈 내리는 소리 |
| `stream` | 계곡·개울 |
| `train_ride` | 기차 창밖 소리 |

### 만다라/프랙탈 (3개)
| 카테고리 | 설명 |
|---------|------|
| `mandala` | 만다라 패턴 명상 |
| `fractal` | 프랙탈 앰비언트 |
| `cosmic_meditation` | 우주·성운 명상 |

---

## 환경변수 (.env)

```env
# AI
ANTHROPIC_API_KEY=...

# 음원
FREESOUND_CLIENT_ID=...
FREESOUND_CLIENT_SECRET=...
JAMENDO_CLIENT_ID=...          # Jamendo 무료 등록 후 발급

# 영상
PEXELS_API_KEY=...

# 업로드
UPLOAD_ENABLED=true
UPLOAD_HOUR_KST=19
UPLOAD_MINUTE_KST=30
SHORTS_UPLOAD_HOUR_KST=18
SHORTS_UPLOAD_MINUTE_KST=30
YOUTUBE_TOKEN=credentials/token.json
YOUTUBE_CLIENT_SECRET=credentials/client_secret.json

# 데이터 암호화
ENCRYPTION_KEY=...             # python crypto_utils.py --generate-key 로 생성
```

---

## 실행

```bash
pip install -r requirements.txt
# FFmpeg 별도 설치 필요: https://ffmpeg.org/download.html

# 자연소리 롱폼 (AI가 카테고리 자동 선택)
python pipeline.py

# 만다라 롱폼 (테스트: 3분 영상)
python pipeline_mandala.py --mode both --test

# 만다라 롱폼 (1시간 풀영상)
python pipeline_mandala.py --mode both

# 만다라 카테고리 지정
python pipeline_mandala.py --category fractal

# 기존 생성 영상 재업로드
python pipeline_mandala.py --upload-only output/mandala_20260530_095436

# Jamendo API 테스트 (Claude API 비용 없음)
python test_jamendo.py
```

---

## GitHub Actions Secrets

| Secret | 용도 |
|--------|------|
| `ANTHROPIC_API_KEY` | Claude Haiku API |
| `FREESOUND_CLIENT_ID` / `_SECRET` | 자연소리 수집 |
| `JAMENDO_CLIENT_ID` | 만다라 음원 수집 |
| `PEXELS_API_KEY` | 영상 수집 |
| `YOUTUBE_TOKEN_JSON` | YouTube 업로드 토큰 |
| `GOOGLE_CLIENT_SECRET_JSON` | YouTube OAuth 클라이언트 |
| `RCLONE_CONF` | Google Drive 백업 |
| `ENCRYPTION_KEY` | used_assets.json 암호화 |

---

## 채널

[@Calmdromeda](https://www.youtube.com/@Calmdromeda)
