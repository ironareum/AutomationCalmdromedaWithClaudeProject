# Calmdromeda — 자동화 파이프라인

> **Calm(잠) + Andromeda(우주)** — 우주 테마 수면음악 YouTube 채널 자동화

채널 링크: [@Calmdromeda](https://www.youtube.com/@Calmdromeda)

---

## 채널 방향성

### 핵심 철학

> "시청자는 우주를 사러 오는 게 아니라 **잠**을 사러 온다."

- **우주**는 차별화 포인트 (빗소리·백색소음 대비 경쟁 낮음)
- **수면**이 메인 가치 — 제목·태그·설명 모두 수면 키워드 중심
- 채널 성장 전략: 바이럴이 아닌 **검색 자산 축적** (롱폼이 핵심)

### 카테고리 (4개 로테이션)

| 카테고리 | 한국어 제목 키워드 | 영어 제목 키워드 |
|---------|-----------------|----------------|
| `galaxy` | 우주 수면음악 | Deep Space Sleep Music |
| `aurora` | 오로라 수면음악 | Aurora Sleep Music |
| `stellar` | 별빛 수면음악 | Starlight Sleep Music |
| `nebula` | 성운 수면음악 | Nebula Sleep Music |

---

## 제목 작성 가이드

### 원칙: 검색 > 감성 (초반 구독자 단계)

구독자가 적은 초반에는 추천 알고리즘보다 **검색 유입**이 주요 진입점.
감성 문구는 검색 유입 후 썸네일·설명에서 커버한다.

### 현재 고정 포맷

```
{카테고리 수면 키워드} | {영문 검색 키워드} | 1 Hour Ambient Sound
```

**예시:**
```
✅ 오로라 수면음악 | Aurora Sleep Music | 1 Hour Ambient Sound
✅ 우주 수면음악 | Deep Space Sleep Music | 1 Hour Ambient Sound
✅ 별빛 수면음악 | Starlight Sleep Music | 1 Hour Ambient Sound
```

### 나쁜 예 vs 좋은 예

| 나쁜 예 (감성 중심) | 좋은 예 (검색 중심) |
|-------------------|------------------|
| 오로라 따라가다 그냥 잠들었어요 | 오로라 수면음악 \| Aurora Sleep Music |
| 우주 속에서 나를 잃어버리는 중 | 우주 수면음악 \| Deep Space Sleep Music |
| Cosmic Nebula Journey | Deep Sleep Music in Space \| Cosmic Ambient |

### 왜 `1 Hour Ambient Sound`를 뒤에 붙이나?

- 영어권 검색어 `"1 hour ambient"`, `"ambient sound sleep"` 포착
- 모든 영상에 반복 → 채널 누적 검색 자산화

---

## 업로드 스케줄

### 현재 운영 스케줄 (코스믹 파이프라인만 활성)

| 요일 | 내용 | Actions 실행 |
|------|------|------------|
| 월 | 롱폼 21:05 공개 | 토 Actions |
| 화 | 숏폼 21:05 공개 | 월 Actions |
| 목 | 롱폼 21:05 공개 | 화 Actions |
| 금 | 숏폼 21:05 공개 | 목 Actions |
| 토 | 숏폼 21:05 공개 | 금 Actions |

- 롱폼/숏폼 같은 날 업로드 없음 → 클릭 분산 방지
- 롱폼 주 2회 + 숏폼 주 3회 = 주 5회 업로드

---

## 파이프라인

### 현재 활성

| 파이프라인 | 파일 | Actions |
|----------|------|---------|
| **코스믹 롱폼** | `pipeline_cosmic.py --mode longform` | `cosmic_longform.yml` |
| **코스믹 숏폼** | `pipeline_cosmic.py --mode shorts` | `cosmic_shorts.yml` |

### 비활성 (보관)

| 파이프라인 | 파일 | 상태 |
|----------|------|------|
| 자연소리 | `pipeline.py` | Actions 스케줄 비활성화 (수동 실행 가능) |
| 만다라/프랙탈 | `pipeline_mandala.py` | Actions 삭제 |

---

## 코스믹 파이프라인 흐름

```
GitHub Actions (목요일 09:00 KST 예시 — 금요일 숏폼 공개)
        │
        ▼
  data 브랜치 → used_assets.json 복원
        │
        ▼
  [Planner] cosmic_concept.py
  · 카테고리 로테이션 (galaxy → aurora → stellar → nebula)
  · Claude Haiku → shorts_intro / shorts_title / 설명 / 태그 생성
  · 제목은 고정 포맷으로 조합 (AI 생성 X)
        │
   ┌────┴────┐
   ▼         ▼
[음원]     [영상]
jamendo.py  pexels.py
ambient/    우주·오로라
meditation  4K 클립
BY·BY-SA    카테고리별
화이트리스트   쿼리
   │         │
   └────┬────┘
        ▼
  [Producer] pipeline_cosmic.py
  · 롱폼: 2-Pass 인코딩 (정규화 → 루프+로고 → 머지)
  · 숏폼: 15s 독립 제작 + 4줄 텍스트 fade 오버레이
        │
   ┌────┴────┐
   ▼         ▼
[썸네일]  [YouTube 예약 업로드]
           days_ahead 기반 공개일 자동 계산
        │
        ▼
  used_assets.json → data 브랜치 저장
  (숏폼 음원은 이력 미등록 — 롱폼 dedup 풀 보존)
```

---

## 음원 라이선스 정책

Jamendo CC **화이트리스트** 방식 — 수익창출 안전:

| 라이선스 | 허용 | 비고 |
|---------|------|------|
| CC BY | ✅ | 출처 표기만 하면 상업 사용 가능 |
| CC BY-SA | ✅ | 출처 표기 + 동일 라이선스 배포 |
| CC BY-NC | ❌ | 비상업적 전용 — 수익창출 불가 |
| CC BY-ND | ❌ | 변형 금지 — 사용 불가 |
| 라이선스 미확인 | ❌ | 빈 값도 차단 |

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| Language | Python 3.11+ |
| AI | Claude Haiku 4.5 (Anthropic API) |
| 음원 | Jamendo API (CC BY / BY-SA만) |
| 영상 | Pexels API (무료 4K) |
| 인코딩 | FFmpeg |
| 텍스트 오버레이 | Pillow + FFmpeg overlay |
| 업로드 | YouTube Data API v3 |
| 자동화 | GitHub Actions |

---

## 로컬 실행

```bash
pip install -r requirements.txt
# FFmpeg 별도 설치 필요

# 테스트 (3분 영상)
python pipeline_cosmic.py --mode both --test

# 롱폼만 (1시간)
python pipeline_cosmic.py --mode longform

# 숏폼만 (15s 독립)
python pipeline_cosmic.py --mode shorts

# 카테고리 지정
python pipeline_cosmic.py --mode both --test --category aurora

# Jamendo API 단독 테스트
python test_jamendo.py
```

---

## 환경변수 (.env)

```env
ANTHROPIC_API_KEY=...
JAMENDO_CLIENT_ID=...
PEXELS_API_KEY=...

UPLOAD_ENABLED=true
UPLOAD_HOUR_KST=21
UPLOAD_MINUTE_KST=5
SHORTS_UPLOAD_HOUR_KST=21
SHORTS_UPLOAD_MINUTE_KST=5
UPLOAD_DAYS_AHEAD=2

YOUTUBE_TOKEN=credentials/token.json
YOUTUBE_CLIENT_SECRET=credentials/client_secret.json
```

---

## GitHub Actions Secrets

| Secret | 용도 |
|--------|------|
| `ANTHROPIC_API_KEY` | Claude Haiku API |
| `JAMENDO_CLIENT_ID` | 음원 수집 |
| `PEXELS_API_KEY` | 영상 수집 |
| `YOUTUBE_TOKEN_JSON` | YouTube 업로드 토큰 |
| `GOOGLE_CLIENT_SECRET_JSON` | YouTube OAuth 클라이언트 |
| `RCLONE_CONF` | Google Drive 백업 |

---

## 프로젝트 구조

```
AutomationCalmdromedaWithClaudeProject/
│
├── pipeline_cosmic.py          # 코스믹 롱폼 + 숏폼 파이프라인 (메인)
├── pipeline.py                 # 자연소리 파이프라인 (비활성)
├── pipeline_mandala.py         # 만다라 파이프라인 (비활성)
├── config.py                   # 환경변수, 경로 설정
│
├── .github/workflows/
│   ├── cosmic_longform.yml     # 코스믹 롱폼 (토·화 → 월·목 공개)
│   ├── cosmic_shorts.yml       # 코스믹 숏폼 (월·목·금 → 화·금·토 공개)
│   └── daily_pipeline.yml      # 자연소리 (스케줄 비활성, 수동만)
│
├── planner/
│   ├── cosmic_concept.py       # 코스믹 콘셉트 생성 (4개 카테고리)
│   ├── concept_generator.py    # 자연소리 콘셉트 생성
│   └── mandala_concept.py      # 만다라 콘셉트 생성 (비활성)
│
├── collector/
│   ├── jamendo.py              # Jamendo 음원 수집 (BY/BY-SA 화이트리스트)
│   └── pexels.py               # Pexels 영상 수집
│
├── producer/
│   ├── ffmpeg_producer.py      # FFmpeg 인코딩, 숏폼 추출
│   └── thumbnail.py            # 썸네일 생성
│
├── uploader/
│   └── youtube.py              # YouTube 예약 업로드
│
└── assets/
    └── fonts/
        └── NanumMyeongjo.ttf   # 숏폼 텍스트 오버레이 폰트
```
