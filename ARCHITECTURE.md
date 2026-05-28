# Calmdromeda — 아키텍처 문서

> 최종 업데이트: 2026-05-27

## 프로젝트 개요

유튜브 힐링/수면 채널 자동화 파이프라인.  
AI 기획 → 음원/영상 수집 → FFmpeg 합성 → 썸네일 생성 → YouTube 예약 업로드까지 전 과정 자동화.

---

## 디렉토리 구조

```
AutomationCalmdromedaWithClaudeProject/
├── pipeline.py              # 메인 파이프라인 (롱폼 1~3시간)
├── shorts_pipeline.py       # 쇼츠 독립 파이프라인 (40초)
├── pipeline_zen.py          # 젠(동양) 파이프라인 (8시간 + 60초 쇼츠)
├── config.py                # 전역 설정 (API 키, 경로, 카테고리 쿼리)
├── collector/
│   ├── freesound.py         # Freesound API 수집 + 로컬 폴백 + AI 검증
│   ├── pexels.py            # Pexels API 영상 수집
│   └── pixabay.py           # Pixabay Music 수집 (zen 파이프라인 전용)
├── planner/
│   ├── concept_generator.py # Claude AI 기반 콘셉트 생성 (일반 카테고리)
│   └── zen_concept.py       # 젠 카테고리 전용 콘셉트 생성
├── producer/
│   ├── ffmpeg_producer.py   # FFmpeg 합성 (믹싱, 루프, 로고 오버레이)
│   └── thumbnail.py         # 썸네일 자동 생성 (Pillow)
├── uploader/
│   └── youtube.py           # YouTube Data API v3 업로드
├── assets/
│   ├── sounds/              # 로컬 음원 캐시 (카테고리별 폴더)
│   │   └── _used/           # 사용된 로컬 음원 이동 보관
│   ├── video/               # 로컬 영상 캐시 (카테고리별 폴더)
│   └── logo*.png            # 채널 로고 이미지
├── used_assets.json         # 사용 이력 DB (세션별 누적)
├── blacklist.json           # 재사용 영구 금지 파일 목록
├── measure_lufs.py          # LUFS 진단 유틸리티
├── print_attribution.py     # 저작자 표시 출력 유틸리티
└── output/
    └── {session_id}/        # 실행별 결과물 폴더
        ├── pipeline.log
        ├── metadata.json
        ├── sounds/
        ├── videos/
        ├── thumbnails/
        └── temp/            # FFmpeg 임시 파일 (완료 후 삭제)
```

---

## 파이프라인 종류

### 1. 메인 파이프라인 (`pipeline.py`)

롱폼 영상 (1~3시간) 생성. 가장 범용적인 파이프라인.

```
Step 1  AI 기획          generate_concept() → concept dict
Step 2  영상 수집         PexelsCollector.collect()
Step 3  음원 수집         FreesoundCollector.collect() (레이어 구조 + AI 검증)
Step 4  FFmpeg 합성       VideoProducer.produce() → final.mp4
Step 5  쇼츠 추출         VideoProducer.extract_shorts_clip() → shorts.mp4
Step 6  썸네일 생성        ThumbnailGenerator.generate()
Step 7  메타데이터 저장     metadata.json
Step 8  YouTube 업로드     YouTubeUploader.upload() × 2 (롱폼 + 쇼츠)
Step 9  used_assets 등록  register_used_session()
Step 10 Google Drive 백업  upload_to_gdrive() via rclone
```

### 2. 쇼츠 파이프라인 (`shorts_pipeline.py`)

쇼츠 전용 40초 영상. 메인 파이프라인과 `used_assets.json`을 공유.

- 음원: main + sub 2레이어만 수집 (point 제외)
- 영상: 1클립
- 음원 수집 실패 시 최대 3회 카테고리 교체 재시도
- YouTube 예약: 매일 18:30 KST

### 3. 젠 파이프라인 (`pipeline_zen.py`)

동양/명상 카테고리 전용. 8시간 롱폼 + 60초 쇼츠.

- 음원: Pixabay Music 우선 → Freesound 폴백
- 영상: 단일 클립 최장 우선 선택
- FFmpeg: 2-Pass (Pass1: 1080p 정규화+루프, Pass2: 오디오 머지, copy 코덱)
- 카테고리: moktak_melodic, tibetan_bowl, temple_chant, zen_instrumental, oriental_ambient

---

## 모듈별 역할

### `config.py`

전역 설정 싱글턴. `.env` 파일에서 API 키 로드.

| 설정 항목 | 값 |
|---|---|
| `video_resolution` | 1920×1080 |
| `video_fps` | 30 |
| `video_bitrate` | 2000k |
| `audio_bitrate` | 192k |
| `thumbnail_size` | 1280×720 |
| `upload_hour_kst` | 19:30 (롱폼) |
| `shorts_upload_hour_kst` | 18:30 (쇼츠) |
| `category_queries` | 카테고리 → Pexels 검색어 매핑 (18개 카테고리) |

---

### `planner/concept_generator.py`

Claude Haiku (`claude-haiku-4-5-20251001`)로 콘셉트 자동 생성.

**카테고리 시스템 (25개)**

| 그룹 | 카테고리 |
|---|---|
| rain_group | rain, rain_thunder, summer_rain |
| nature_group | forest, birds, camping |
| water_group | ocean, hot_spring, underwater |
| indoor_group | cafe, library, study_room, fireplace_rain |
| travel_group | airplane, subway, train_ride |
| ambient_group | white_noise, bath_house |
| winter_group | winter_snow, snow_walk |
| water_drip_group | stream, cave_water, ice_melt |
| zen_group | moktak |
| transit_group | summer_night |

**카테고리 순환 전략 (`_pick_category`)**

1. 같은 그룹이 연속되지 않도록 그룹 기반 선택
2. 최근 7회 사용 카테고리 스킵
3. 부족하면 최근 2회만 스킵으로 완화

**`generate_concept()` 반환 구조**

```python
{
    "title":         "빗소리 ASMR | 스르르 잠드는 밤 | Rain for Sleep",
    "shorts_title":  "빗소리에 잠드는 밤 #빗소리ASMR",
    "category":      "rain",
    "mood":          "차분하고 포근한",
    "duration_hours": 1,
    "tags":          [...],           # AI 생성 + 카테고리 + 공통 태그 합산 (max 50)
    "sounds":        [...],           # Freesound 검색어 목록
    "sound_layers":  {               # 레이어별 검색어 목록
        "intro": [...],
        "main":  [...],
        "sub":   [...],
        "point": [...],
    },
    "video_queries": [...],           # Pexels 검색어 1개
    "description_en": "...",
    "subtitle_en":    "Rain for Sleep",
    "language":       "ko",
}
```

**`skip_categories` 파라미터**: 쇼츠 파이프라인 재시도 시 실패 카테고리를 recent_cats 앞에 추가해 `_pick_category`가 건너뛰도록 함.

---

### `collector/freesound.py`

Freesound.org API + 로컬 음원 폴더 통합 수집. 프로젝트 핵심 모듈.

**주요 상수**

| 상수 | 값 | 설명 |
|---|---|---|
| `LUFS_SOURCE_MIN` | -50.0 | LUFS 하한 (이 값 미만 파일 수집 제외) |
| `MAX_DOWNLOAD_SIZE_MB` | 50 | 단일 파일 최대 크기 |
| `USED_ASSETS_FILE` | used_assets.json | 세션 이력 파일 |
| `BLACKLIST_FILE` | blacklist.json | 영구 제외 파일 목록 |

**레이어 구조 (`_collect_by_layers`)**

```
intro  — 1파일, 5초 이상, 영상 시작 1회만 재생 (파일명에 intro_ 접두사)
main   — 60초 이상, 핵심 환경음 (루프)
sub    — 10초 이상, 보조 레이어 (루프)
point  — 10초 이상, 포인트 사운드 (루프, 라이브러리 카테고리는 침묵 간격 삽입)
```

**AI 검증 (`_ai_filter_sounds`)**

Claude Haiku가 다운로드된 파일명을 콘셉트와 대조해 부적합 파일 제거.  
판단 기준: 카테고리 부합 여부, 무드 일치, 저작권 안전성 (battlescene·총소리 등 제외).

**수집 흐름**

```
collect() 호출
  ├─ sound_layers 있음 → _collect_by_layers()
  │     ├─ 레이어별 Freesound API 검색 + LUFS 스크리닝
  │     ├─ AI 검증 (_ai_filter_sounds)
  │     └─ 결과 반환 (0개면 파이프라인 재시도 루프가 처리)
  └─ sound_layers 없음 → 로컬 폴더 우선 → API → 로컬 폴백
```

**주요 함수**

| 함수 | 역할 |
|---|---|
| `load_used_assets()` | used_assets.json 전체 로드 |
| `register_used_session()` | 세션 완료 후 이력 등록 |
| `is_sound_used(name)` | 중복 수집 방지 체크 |
| `is_video_used(video_id)` | 영상 중복 체크 |

---

### `collector/pexels.py`

Pexels API로 자연 영상 수집. 로컬 영상 폴더 우선.

- 사람 포함 영상 필터링 (URL/태그에 people·man·woman 등 키워드 감지)
- 긴 영상 우선 정렬 (duration 내림차순)
- 해상도 우선순위: 4K > 1440p > 1080p > 720p

**수집 흐름**

```
collect()
  ├─ assets/video/{category}/ 로컬 파일 확인
  ├─ 로컬 충분하면 API 스킵
  └─ 부족분 Pexels API 보충
```

---

### `collector/pixabay.py`

Pixabay Music API 수집. **젠 파이프라인 전용**.

- 상업적 사용 무료, 저작자 표시 불필요 (Pixabay License)
- API 응답의 audio URL 필드명 버전별 다중 시도 (`audio`, `audioURL`, `audioUrl` 등)
- `used_assets.json` 기반 중복 방지

---

### `producer/ffmpeg_producer.py`

FFmpeg 기반 영상 합성 엔진. 오디오 믹싱·루프·LUFS 정규화·로고 오버레이 처리.

**주요 상수**

| 상수 | 값 | 설명 |
|---|---|---|
| `LUFS_SOURCE_MIN` | -50.0 | 제작 단계 소스 LUFS 하한 (freesound.py와 동일) |

**`mix_sounds()` 처리 흐름**

```
1. intro 분리 (파일명 intro_ 접두사)
2. regular 파일 개별 LUFS 측정 → -50 미만 제외 (excluded_sources 기록)
3. 상위 3개 → main/sub/point 레이어 할당 (duration 내림차순)
4. 각 파일 seamless loop 처리 (acrossfade 5초)
5. 레이어별 볼륨 자동 계산 (source LUFS → target 볼륨 역산)
6. FFmpeg amix → highpass@80Hz → EQ@3kHz → 페이드아웃 5초
7. LUFS 후처리:
   - ≥ -20: loudnorm 스킵 (이미 충분)
   - -20 ~ -24: loudnorm 적용
   - < -24: 스킵 (과부스트 왜곡 위험)
8. 192k MP3 출력
```

**`prepare_video_loop()` 처리 흐름**

```
1. 각 클립 → 1080p, 24fps 정규화 (CRF 28, preset medium)
2. FFmpeg concat demuxer로 이어붙임
3. target_duration에 맞게 루프
4. 정규화 임시 파일 즉시 삭제
```

**`produce()` 최종 출력**

```python
(final_video.mp4, actual_sounds[], actual_videos[], audio_lufs, source_lufs, excluded_sources)
```

**`extract_shorts_clip()`**

1080×1920 (9:16) 크롭. 중앙 608px 추출 → 1080×1920 스케일. 3초부터 시작.

---

### `producer/thumbnail.py`

Pillow 기반 썸네일 자동 생성 (1280×720 JPEG).

**렌더링 레이어 순서**

```
1. 배경: 영상 3초 지점 프레임 추출 (FFmpeg) → 실패 시 그라디언트
2. 다크 오버레이: y값 기반 가변 알파 (60~160)
3. 글로우 이펙트: 카테고리별 컬러 타원 (theme glow color)
4. 텍스트: 부제(소) → 메인 제목(2줄, 38~100px 자동조정) → 영문 부제(이탤릭)
5. 로고: 좌상단 heading (폭의 17%) + 우하단 원형 (180px, 60% 불투명도)
```

**제목 파싱 규칙**

`"빗소리 ASMR | 스르르 잠드는 밤 | Rain for Sleep"` → pipe 분리  
- [0]: 메인 표시 텍스트
- [1]: 감성 부제 (subtitle)
- [2]: 영문 SEO 부제 (subtitle_en)

**카테고리 테마**: 20개 카테고리별 glow 색상 팔레트 (rain→파란 glow, forest→녹색, cafe→갈색 등).

---

### `uploader/youtube.py`

YouTube Data API v3. 10MB 청크 resumable upload + 썸네일 + 예약 공개.

- privacy: `private` + `publishAt` (항상 다음날 지정 시각)
- OAuth 2.0: 토큰 자동 갱신 (`token.json`)
- 실패 시 `None` 반환, 파이프라인은 경고 후 계속

---

## 모듈 의존 관계

```
pipeline.py / shorts_pipeline.py / pipeline_zen.py
  ├── config.py
  ├── planner/concept_generator.py  ──→  anthropic (Claude Haiku)
  ├── planner/zen_concept.py        ──→  anthropic (Claude Haiku)
  ├── collector/freesound.py        ──→  requests, used_assets.json
  │     └── _ai_filter_sounds()     ──→  anthropic (Claude Haiku)
  ├── collector/pexels.py           ──→  requests, freesound.load_used_assets()
  ├── collector/pixabay.py          ──→  requests, freesound.load_used_assets()
  ├── producer/ffmpeg_producer.py   ──→  subprocess (ffmpeg)
  ├── producer/thumbnail.py         ──→  Pillow, subprocess (ffmpeg)
  └── uploader/youtube.py           ──→  google-api-python-client
```

**공유 상태 파일**

| 파일 | 용도 | 읽기 모듈 | 쓰기 모듈 |
|---|---|---|---|
| `used_assets.json` | 사용 이력 (중복 방지) | freesound, pexels, pixabay, concept_generator | freesound.register_used_session() |
| `blacklist.json` | 영구 제외 파일 | freesound | 수동 편집 |
| `output/{id}/sources.json` | 저작자 정보 | pipeline (description 생성) | pexels, freesound |
| `output/{id}/metadata.json` | 세션 메타데이터 | - | pipeline |

---

## 데이터 흐름 전체

```
.env (API 키)
    ↓
Config
    ↓
[AI 기획] generate_concept() / generate_zen_concept()
    ↓  concept dict (title, category, sound_layers, video_queries, ...)
[음원 수집] FreesoundCollector._collect_by_layers()
    ├─ Freesound API → 다운로드 → LUFS 스크리닝
    └─ _ai_filter_sounds() → 부적합 파일 제거
    ↓  sound_files[] (Path)
[영상 수집] PexelsCollector.collect() / PixabayMusicCollector.collect()
    ↓  video_files[] (Path)
[합성] VideoProducer.produce()
    ├─ mix_sounds() → mixed_audio.mp3
    ├─ prepare_video_loop() → video_loop.mp4
    └─ merge() + add_logo_overlay() → final.mp4
    ↓  (final.mp4, used_sounds, used_videos, lufs_info)
[쇼츠 추출] extract_shorts_clip() → shorts.mp4
[썸네일] ThumbnailGenerator.generate() → thumb.jpg
[업로드] YouTubeUploader.upload()
    ↓  {video_id, url, publish_at}
[이력 등록] register_used_session() → used_assets.json
[백업] upload_to_gdrive() via rclone → Google Drive
```

---

## 주요 설계 결정 및 변경 이력

### 음원 품질 관리

**LUFS 이중 스크리닝**  
수집 단계(`freesound.py:LUFS_SOURCE_MIN=-50.0`)와 제작 단계(`ffmpeg_producer.py:LUFS_SOURCE_MIN=-50.0`) 두 곳에서 동일한 임계값으로 필터링.  
초기값은 -28 → -35 → -50으로 완화됨 (조용한 환경음 카테고리 대응).

**AI 검증 레이어**  
다운로드 후 Claude Haiku가 파일명과 콘셉트를 대조해 부적합 파일 제거.  
AI가 거부한 파일은 보충 수집 대상에서도 완전 제외 (이전에는 `_supplement_sounds`가 AI 검증 없이 재수집하는 버그 있었음 → 제거).

**`_supplement_sounds` 제거 (PR #44)**  
sound_layers 경로에서 `_supplement_sounds` 호출 제거.  
음원 0개 → 파이프라인 카테고리 재시도 루프가 처리, 1개 → 그대로 사용.

### 카테고리 재시도 (shorts_pipeline.py)

음원 수집 실패 시 최대 3회 카테고리 교체 재시도.  
`skip_categories` 파라미터로 실패한 카테고리를 `generate_concept()`에 전달 → `_pick_category`가 해당 카테고리 스킵.

### 콘텐츠 품질

- 영상 쿼리: 3~4개 → 1개로 축소 (제목-영상 불일치 감소)
- 영상 클립: 쇼츠에서 2클립 → 1클립
- 금지 표현: '소복이', '사르르', '포슬포슬' (AI 프롬프트에 명시)

### Seamless Loop

음원 끊김 방지를 위해 `acrossfade=d=5`로 파일 끝을 시작부와 크로스페이드.  
`stream_loop`과 조합해 무한 루프 시 청각적으로 자연스러운 연결.

---

## 유틸리티

| 파일 | 용도 |
|---|---|
| `measure_lufs.py` | 특정 파일의 LUFS 수동 측정 (파이프라인 외부 진단용) |
| `print_attribution.py` | used_assets.json 기반 저작자 표시 출력 |
| `extract_pipeline_logs.py` | 로그 파싱/분석 |
| `analyze.py` | 수집 음원 분석 |
| `crypto_utils.py` | 자격증명 암호화/복호화 유틸 |
| `test_mix.py` | 오디오 믹싱 수동 테스트 |
| `tests/test_pipeline.py` | 파이프라인 단위 테스트 |

---

## 환경 변수 (.env)

```
FREESOUND_API_KEY=...
PEXELS_API_KEY=...
PIXABAY_API_KEY=...         # zen 파이프라인
ANTHROPIC_API_KEY=...
YOUTUBE_CLIENT_SECRET=credentials/client_secret.json
YOUTUBE_TOKEN=credentials/token.json
UPLOAD_ENABLED=true
UPLOAD_HOUR_KST=19          # 롱폼 예약 시각
UPLOAD_MINUTE_KST=30
SHORTS_UPLOAD_HOUR_KST=18   # 쇼츠 예약 시각
SHORTS_UPLOAD_MINUTE_KST=30
```

## 외부 의존성

| 패키지 | 용도 |
|---|---|
| `anthropic` | Claude Haiku API (기획, AI 음원 검증) |
| `requests` | Freesound / Pexels / Pixabay API 호출 |
| `Pillow` | 썸네일 이미지 합성 |
| `google-api-python-client` | YouTube Data API v3 |
| `google-auth-oauthlib` | YouTube OAuth 2.0 |
| `python-dotenv` | .env 파일 로드 |
| `cryptography` | 자격증명 암호화 |
| `ffmpeg` (시스템) | 영상/음원 합성 |
| `rclone` (시스템) | Google Drive 백업 |
