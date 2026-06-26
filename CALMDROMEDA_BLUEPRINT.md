# CALMDROMEDA BLUEPRINT

> **"Calmdromeda creates the experience of falling asleep among the stars."**
> **"캄드로메다는 별들 사이에서 잠드는 경험을 만든다."**

이 문서는 코드가 바뀌어도, AI 모델이 바뀌어도, 채널이 커져도 흔들리지 않는 기준점이다.
새로운 기능 추가 전 반드시 확인: **이것이 이 미션에 맞는가?**

---

## 0. Document Information

| 항목 | 내용 |
|------|------|
| **Purpose** | 캄드로메다 브랜드 헌법 + 기술 설계서 |
| **Scope** | 콘텐츠 전략, 프롬프트 기준, 비주얼 아이덴티티, 기술 아키텍처 |
| **Status** | v1.0 Frozen |

### Version History

| 버전 | 날짜 | 주요 변경 |
|------|------|---------|
| v1.0 | 2026-06-26 | 초기 아키텍처 확정. 3계층 구조, 5-Part 프롬프트, 서브컨셉 시스템 |

---

## 1. Brand Philosophy

### 왜 이 브랜드가 존재하는가

> "시청자는 우주를 사러 오는 게 아니라 **잠**을 사러 온다."

대부분의 수면음악 채널은 음악을 제공한다. 캄드로메다는 **경험**을 제공한다.

- **수면**: 메인 가치 — 모든 제목, 태그, 설명은 수면 중심
- **우주**: 차별화 포인트 — 빗소리/백색소음 대비 경쟁 낮음, 세계관 구축 가능

### 핵심 포지셔닝

```
"수면음악 채널" (X)
"우주를 여행하다가 잠드는 채널" (O)
```

이 채널에서 우주는 배경이 아니다. 우주는 잠드는 장소다.

---

## 2. Brand Identity

### 브랜드 성격

- 조용하고 담담하다
- 문학적이지만 어렵지 않다
- 감정을 강요하지 않는다
- 설명하지 않고 경험하게 한다

### 핵심 키워드

`우주` `잠` `기억` `고요` `여행` `밤` `별`

### 절대 하지 않는 것

- 직접 화법으로 시청자에게 말 걸기 ("당신", "너", "잘 자요")
- 교훈, 위로, 자기계발 메시지
- 과장된 감정 표현
- AI 특유의 시적 클리셰 ("은하의 숨결", "우주의 속삭임")

---

## 3. Content Architecture

### 3계층 구조

```
Category (브랜드 — 4개 고정)
        ↓
Sub Concept (콘텐츠 — 무한 확장)
        ↓
Story (감성 — 매번 AI 생성)
```

**예시:**
```
Galaxy → Milky Way → 별빛이 오늘은 유난히 가까웠다.
Nebula → Purple Nebula → 보랏빛 안개가 천천히 흘렀다.
```

### Category (4개)

| ID | 한국어 | 영어 | 컬러 |
|----|--------|------|------|
| `galaxy` | 은하/딥스페이스 | Galaxy | `#5B7FFF` |
| `aurora` | 오로라 | Aurora | `#67D5C8` |
| `nebula` | 성운 | Nebula | `#9A7BFF` |
| `stellar` | 별/달/밤하늘 | Stellar | `#D8DDE8` |

Stellar = 달, 별, 유성우, 별자리, 별가루 등 "하늘을 올려다본 밤" 전체 포함

### Sub Concept (v1.0 스타터 20개)

카테고리당 5개. `planner/subconcepts.py` 참조.
새 서브컨셉 추가 시 `subconcepts.py`만 수정.

### Category Rotation

```
galaxy → aurora → nebula → stellar → galaxy (고정 순환)
```

Sub Concept 선택: 최근 10개 제외 → priority 가중 랜덤

### Data Structure (used_assets.json)

```json
{
  "cosmic_YYYYMMDD_HHMMSS": { "세션 데이터" },
  "category_index": 2,
  "used_subconcepts": ["milky_way", "aurora", "moonlight"],
  "statistics": {
    "milky_way": { "used": 14 }
  },
  "series": {
    "longform": 27,
    "shorts": 0
  }
}
```

---

## 4. Content Standards

### 쇼츠 (15초)

- **컨셉**: "우주를 여행하다 잠든 사람이 다음 날 희미하게 떠올린 기억의 조각"
- **텍스트**: 4줄, 줄당 8~15자, 마침표 사용
- **화자**: 항상 '나'. 1인칭 경험
- **시간**: 항상 밤
- **끝**: 여운으로 마무리

### 롱폼 (1시간)

- 2-Pass FFmpeg 인코딩 (normalize → loop + logo → merge copy)
- 썸네일: Sub Concept 키워드 + 시리즈 번호
- 카테고리별 Jamendo 음악 특성에 맞는 vartag 필터링

### 제목 포맷

```
{seo_ko} | {seo_en} | 1 Hour Ambient Sound
```

**예시:**
```
은하수 수면음악 | Milky Way Sleep Music | 1 Hour Ambient Sound
달빛 수면음악 | Moonlight Sleep Music | 1 Hour Ambient Sound
```

규칙:
- 검색 유입이 최우선 (감성 문구는 썸네일/설명에서)
- `1 Hour Ambient Sound` 고정 후미 → 영어권 검색 축적

### 설명 (Description)

- 한국어 2~3문장: 전문 용어 금지, 소리를 풍경으로 묘사
- 채널 고정 구분선 + 음원 라이선스 정보
- 태그: 한영 혼합, 최대 50개

### 메타데이터 태그

```
공통: Calmdromeda, 캄드로메다, 수면음악, Sleep Music, Cosmic Ambient...
카테고리별: 오로라, Aurora Ambient, Northern Lights Music...
AI 생성: 서브컨셉별 5~8개
```

---

## 5. Prompt Standards

### Persona (변하지 않는 정의)

```
당신은 'Calmdromeda'의 전속 작가입니다.
시인 X. 자기계발 작가 X. 명언 작가 X.
우주를 여행하다 잠든 사람이 다음 날 희미하게 기억나는 장면을
메모장에 4줄만 적는 사람입니다.
```

### 5-Part Prompt 구조

```
[PERSONA]  캄드로메다 전속 작가 정의
[PART 1]   브랜드 철학 (우주에서 잠드는 경험)
[PART 2]   문체 (담백, 쉬운 단어, AI 과장 금지)
[PART 3]   출력 규칙 (4줄, 8~15자, 마침표, 첫줄 패턴 금지)
[PART 4]   절대 금지 목록
[PART 5]   입력값 (Sub Concept + Mood 2~3개 + Sensory 2개 + Memory Keywords)
```

구현: `planner/prompt_builder.py`

### 금지 규칙

| 규칙 | 이유 |
|------|------|
| 감정 직접 표현 | 감각(경험)으로 대체 |
| "오늘은"으로 시작 | 일기 → 기억으로 전환 |
| 독자에게 말 걸기 | 브랜드 세계관 유지 |
| AI 과장 표현 | 담백한 문체 유지 |

---

## 6. Visual Identity

### Core Brand Colors

| 이름 | HEX | 용도 |
|------|-----|------|
| Cosmic Navy | `#08111F` | 배경 베이스 |
| Moon White | `#F3F6FB` | 본문 텍스트 |
| Aurora Cyan | `#46E5D6` | 브랜드 포인트 (채널 로고 등) |

### Content Color System

| 카테고리 | 메인 컬러 | 보조 컬러 |
|---------|---------|---------|
| Galaxy | `#5B7FFF` | — |
| Aurora | `#67D5C8` | — |
| Nebula | `#9A7BFF` | — |
| Stellar | `#D8DDE8` | — |

**적용 규칙**: 시리즈 키워드 텍스트에만 카테고리 컬러. 나머지는 Moon White.

### 썸네일 레이아웃 (v1.0)

```
[배경: 영상 첫 프레임 + 다크 오버레이]
[글로우: 카테고리 컬러 기반 중앙 타원]

Space Journey          ← 작은 흰색 (시리즈 레이블)
#001                   ← 중간 흰색 (시리즈 번호)
MILKY WAY              ← 큰 카테고리 컬러 (박스 높이 H×20%, 폭 자동 축소)
```

### 시리즈 번호 규칙

- 롱폼에만 적용 (`Space Journey #001`)
- `used_assets.json` → `series.longform` 카운트
- 롱폼 제작 성공 시 +1 저장

### 브랜딩 로고

- v1.0: 미구현 (IDEAS.md 참조)
- 계획: 좌상단 "CALMDROMEDA · Space Sleep Series" 텍스트 오버레이

---

## 7. Publishing Standards

### 업로드 스케줄 (v1.0)

| 실행일 | 공개일 | 콘텐츠 |
|--------|--------|--------|
| 토(UTC) | 월 21:05 | 롱폼 |
| 화(UTC) | 목 21:05 | 롱폼 |
| 월(UTC) | 화 21:05 | 숏폼 |
| 목(UTC) | 금 21:05 | 숏폼 |
| 금(UTC) | 토 21:05 | 숏폼 |

- 롱폼 + 숏폼 같은 날 공개 없음 → 클릭 분산 방지
- 주 2회 롱폼 + 주 3회 숏폼 = 주 5회 업로드

### 음원 라이선스 정책

Jamendo CC **화이트리스트** (수익창출 안전):

| 라이선스 | 허용 |
|---------|------|
| CC BY | ✅ |
| CC BY-SA | ✅ |
| CC BY-NC | ❌ |
| CC BY-ND | ❌ |
| 미확인/공백 | ❌ |

### SEO 정책

- 제목: 검색 우선 (감성보다 키워드)
- 태그: 한영 혼합, 롱테일 키워드 포함
- 설명: 첫 2문장에 핵심 키워드 포함
- 채널 성장 전략: 바이럴이 아닌 **검색 자산 축적** (롱폼이 핵심)

---

## 8. Technical Architecture

### 플랫폼 구조

```
[Platform Core — 재사용 가능]
planner/rotation.py        카테고리 로테이션 + 히스토리
planner/prompt_builder.py  5-Part 프롬프트 엔진
producer/thumbnail.py      규칙 기반 썸네일 생성
uploader/youtube.py        YouTube 업로드

[Brand Config — 채널마다 교체]
planner/subconcepts.py     서브컨셉 데이터 (이것만 바꾸면 새 채널)
CALMDROMEDA_BLUEPRINT.md   브랜드 헌법
```

### 파일 구조

```
AutomationCalmdromedaWithClaudeProject/
├── pipeline_cosmic.py          메인 파이프라인 (롱폼 + 숏폼)
├── config.py                   환경변수
├── CALMDROMEDA_BLUEPRINT.md    브랜드 헌법 (이 문서)
├── IDEAS.md                    v1.0 이후 아이디어 백로그
│
├── planner/
│   ├── subconcepts.py          서브컨셉 DB (데이터)
│   ├── rotation.py             카테고리 로테이션 (선택 로직)
│   ├── prompt_builder.py       5-Part 프롬프트 빌더
│   └── cosmic_concept.py       콘셉트 생성 오케스트레이터
│
├── collector/
│   ├── jamendo.py              Jamendo 음원 수집
│   └── pexels.py               Pexels 영상 수집
│
├── producer/
│   ├── ffmpeg_producer.py      FFmpeg 인코딩
│   └── thumbnail.py            썸네일 생성
│
├── uploader/
│   └── youtube.py              YouTube 예약 업로드
│
└── .github/workflows/
    ├── cosmic_longform.yml     롱폼 자동화 (토·화 실행)
    └── cosmic_shorts.yml       숏폼 자동화 (월·목·금 실행)
```

### 데이터 흐름

```
GitHub Actions (스케줄)
        ↓
rotation.py → Category 로테이션 + Sub Concept 선택
        ↓
prompt_builder.py → 5-Part 프롬프트 조립
        ↓
Claude Haiku → shorts_intro(4줄) + title + description + tags
        ↓
     ┌──┴──┐
jamendo   pexels
음원 수집  영상 수집
     └──┬──┘
        ↓
FFmpeg 인코딩 (롱폼 2-Pass / 숏폼 15s + 텍스트 오버레이)
        ↓
thumbnail.py → 썸네일 생성 (Sub Concept + 시리즈 번호)
        ↓
YouTube 예약 업로드
        ↓
used_assets.json → data 브랜치 저장
```

---

## 9. Future Roadmap

### v1.0 (현재)

- [x] 3계층 구조 (Category → Sub Concept → Story)
- [x] 5-Part 프롬프트 시스템
- [x] 서브컨셉 20개 스타터 세트
- [x] 카테고리별 컬러 시스템
- [x] 시리즈 번호 (Space Journey #001)
- [x] used_assets.json 통합 관리 (rotation + statistics + series)
- [x] priority / enabled 필드 (미래 학습 준비)

### v2.0 (Ideas.md 참조)

- YouTube Analytics → statistics 자동 업데이트
- priority 자동 조정 (성과 기반)
- 브랜딩 로고 오버레이
- 복수 채널 지원

---

## 10. Decision Log

### v1.0 — 2026-06-26

| 결정 | 이유 | 대안 | 채택 이유 |
|------|------|------|---------|
| 카테고리 4개 고정 | 단순한 구조 유지 | 카테고리 무한 확장 | 채널 홈 일관성, 운영 복잡도 감소 |
| Sub Concept 무한 확장 | 반복 방지, 다양성 | 카테고리 확장 | 카테고리 유지 + 소재 다양화 |
| statistics를 객체형으로 | v2 확장 대비 | 단순 카운터 | `{"used": 3}` → `{"used": 3, "views": 14000}` 무변경 가능 |
| series를 longform/shorts 분리 | 미래 숏폼 번호 대비 | 단일 카운터 | 콘텐츠 유형별 독립 추적 |
| 쇼츠를 "기억" 컨셉으로 | 브랜드 세계관 유지 | "일기" 스타일 | "오늘 별을 봤다" (일기) vs "별이 많았다" (기억) — 분위기 차이 결정적 |
| 감정보다 감각 | AI 특유 과장 방지 | 감정 표현 허용 | "행복했다" X → "발걸음이 느려졌다" O — 장면 상상 유도 |
| 5-Part 프롬프트 분리 | 유지보수 편의 | 단일 프롬프트 | PART 추가/삭제 시 sections 리스트만 수정 |
| subconcepts.py 별도 파일 | SRP 원칙 | cosmic_concept.py 내부 | 서브컨셉 추가 시 로직 파일 미수정 |
| rotation.py 별도 분리 | 테스트 가능성 | cosmic_concept.py 내부 | 선택 로직 단독 테스트 가능 |
| used_assets.json 확장 (신규 DB X) | 현재 규모 적합 | 별도 DB | JSON이 가장 관리하기 쉬운 현재 단계 |
| priority 필드 미리 추가 | 미래 학습 준비 | 필요 시 추가 | `priority = f(조회수, CTR)` 전환 시 구조 변경 최소화 |
| Freeze v1.0 | 기능 스코프 관리 | 계속 추가 | "이것도 넣을까?" → IDEAS.md. v1이 끝날 때까지 절대 추가 X |
