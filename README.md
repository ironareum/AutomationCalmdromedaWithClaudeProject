# calmdromeda YouTube Automation Pipeline

자연 사운드 유튜브 영상 자동 생성 파이프라인

## 프로젝트 구조

```
AutomationCalmdromedaWithClaudeProject/
└── assets/
│   ├── logo.png   # Calmdromeda.PNG 파일을 여기에 logo.png로 저장
│   ├── fonts/     
│   └── sounds/    # Freesound 점검중일때 임시로 사용할 음원 저장
│       ├── rain/
│       │   └── rain_01.mp3
│       ├── ocean/
│       ├── forest/
│       ├── thunder/
│       ├── cafe/
│       └── camping/
├── collector/
│   ├── freesound.py     # 사운드 수집 (Freesound API)
│   └── pexels.py        # 영상 수집 (Pexels API)
├── output/20260329_005810/
│   ├── pipeline.log        ← 신규 (DEBUG 레벨, 전체 로그 + 스택 트레이스)
│   ├── metadata.json
│   ├── thumbnails/
│   ├── sounds/             ← 실제 사용한 파일만
│   ├── videos/             ← 실제 사용한 파일만
│   └── 빗소리_ASMR_final.mp4
├──producer/
│   ├── ffmpeg_producer.py  # 영상 합성 (FFmpeg)
│   └── thumbnail.py        # 썸네일 자동 생성
├──uploader/
│   └── youtube.py   ← YouTube Data API v3 업로드 + 예약 공개
├── .env                 # API 키 템플릿
├── .gitignore
├── config.py            # 설정 (카테고리, API, 경로)
├── history.txt          # 개발이력관리
├── pipeline.py          # 메인 실행 파일
├── README.md            # 프로젝트 소개
└── requirements.txt

```

## 설치

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. FFmpeg 설치

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows
# https://ffmpeg.org/download.html
```

### 3. API 키 발급

| API | 발급 URL | 비용 |
|-----|---------|------|
| Freesound | https://freesound.org/apiv2/apply/ | 무료 |
| Pexels | https://www.pexels.com/api/ | 무료 |
| YouTube Data API | https://console.cloud.google.com | 무료 (쿼터 있음) |
| Anthropic (Phase 2) | https://console.anthropic.com | 매우 저렴 |

### 4. .env 파일 생성

```bash
cp .env.example .env
# .env 파일 열어서 API 키 입력
```

## 실행

```bash
python pipeline.py
```

## 커스텀 콘셉트 실행

`pipeline.py` 하단의 `test_concept` 수정:

```python
concept = {
    "title": "Gentle Ocean Waves at Night | 3 Hours Sleep",
    "category": "ocean",           # config.py의 category_queries 참고
    "sounds": ["ocean waves", "gentle waves", "beach waves"],
    "mood": "peaceful and calming",
    "duration_hours": 3,
    "tags": ["ocean sounds", "sleep sounds", "waves", "beach", "white noise"]
}
```

## 카테고리 목록

| category | 내용 |
|----------|------|
| `rain` | 빗소리 |
| `rain_thunder` | 빗소리 + 천둥 |
| `ocean` | 파도/바다 |
| `forest` | 숲 환경음 |
| `birds` | 새소리 |
| `white_noise` | 백색소음 |
| `cafe` | 카페 분위기 |
| `camping` | 캠핑/모닥불 |

## Phase 2 (예정)

- Claude API로 트렌딩 기반 콘텐츠 기획 자동화
- YouTube Data API 업로드 자동화
- GitHub Actions로 매일 자동 실행
- 성과 트래킹 및 포맷 최적화

Phase 2 - YouTube 자동 업로드
실행 전 준비사항
1. API 활성화
    https://console.cloud.google.com → 프로젝트 선택
    API 및 서비스 → 라이브러리 → YouTube Data API v3 → 사용 설정

2. OAuth 2.0 클라이언트 ID 생성
    API 및 서비스 → 사용자 인증 정보 → + 사용자 인증 정보 만들기
    OAuth 클라이언트 ID 선택
    애플리케이션 유형: 데스크톱 앱
    JSON 다운로드 → 프로젝트의 credentials/client_secret.json 으로 저장

3. OAuth 동의 화면
    테스트 사용자에 본인 Google 계정 추가

4. 라이브러리 설치: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2