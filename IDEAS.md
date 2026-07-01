# Calmdromeda — Ideas Backlog

v1.0이 완성될 때까지 여기에만 적는다. 절대 v1.0에 넣지 않는다.

---

## 콘텐츠

- Black Space 스페셜 시리즈 (블랙홀, 암흑우주) — 영상 100개 이상 쌓인 후
- 계절/이벤트 스페셜 (크리스마스 밤하늘, 새해 유성우 등)
- 한국어/영어 분리 채널 운영 검토

## 썸네일

- 자동 썸네일 A/B 테스트 (CTR 기반 우승자 선택)
- 썸네일 AI Vision 분석 (영상 베스트 프레임 자동 선택)

## 음악

- Jamendo 외 추가 소스 (Free Music Archive, ccMixter 등)
- 자체 BGM 생성 (Suno, Udio 등 AI 음악 도구)

## 데이터 & 자동화

- YouTube Analytics API 연동 → 조회수/CTR/평균시청시간 수집
- statistics 기반 priority 자동 업데이트 (성과 좋은 서브컨셉 우선 노출)
- 복수 채널 지원 (채널별 subconcepts.py 교체만으로 운영)
- Google Sheets 대시보드 자동 업데이트

## 플랫폼

- 캄드로메다 v2: 제2 채널 런칭 (다른 컨셉 — 예: 빗소리, 자연소리)
- GitHub Actions → n8n 또는 Airflow 전환 검토 (워크플로우 복잡도 증가 시)

---

## 문서 구조 개편

- README.md → 실행 가이드만 (소개/설치/실행/구조/License)
- CALMDROMEDA_BLUEPRINT.md → 브랜드 헌법 유지 (철학/카테고리/규칙/프롬프트/Decision Log)
- ARCHITECTURE.md 신규 → 개발자 문서 (Pipeline/Data Flow/used_assets/Actions/Planner/Producer/Uploader)
- docs/legacy/ 신규 → 이전 컨셉 보존 (nature_pipeline.md, mandala_pipeline.md, zen_pipeline.md)
- README 문서 네비게이션: README → Blueprint → Architecture → Legacy → Ideas 링크 구조

---

## 리뷰 기준 (CLAUDE.md 추가 예정)

새 요청이 오면 아래 순서로 검토:

1. Blueprint와 일치하는가? (브랜드 철학 / 문체 규칙 / 데이터 구조)
2. 설계가 유지되는가? (책임 분리 / 확장성 / 데이터-로직 분리)
3. 구현 품질은? (중복 / 테스트 가능성 / 유지보수)

새 아이디어가 오면 먼저 질문: **"이게 Blueprint를 바꾸는 일인가, 구현을 바꾸는 일인가?"**
- Blueprint를 바꾸는 일 → 신중하게 (브랜드 기준이 바뀌는 것)
- 구현을 바꾸는 일 → 비교적 자유롭게 (더 나은 방법이면 개선)
