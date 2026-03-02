# Social Trend Analyzer (Threads + Instagram)

Meta 공식 API(Threads / Instagram Graph API)를 사용해 특정 토픽(키워드/해시태그)의 게시물을 수집하고, **트렌드 점수(0–100)** 및 **Organic vs Paid/Promoted** 신호를 계산하는 CLI 도구입니다.

- **패키지/CLI 이름**: `trend-analyzer`
- **Python**: 3.10+
- **기본 동작**: API 토큰이 없으면 자동으로 **Demo 모드**로 실행

## What it does

- **Collect** posts for a given topic
  - Instagram: 해시태그 기반 최근 미디어 수집 (Graph API)
    - Instagram API는 자유 키워드 검색이 아니라 **해시태그 검색**만 지원하므로, 입력 토픽은 내부에서 해시태그 형식으로 정리되어 조회됩니다.
  - Threads: 키워드 검색 스크래퍼 구현 (Threads API)
- **Analyze** trend strength using 3 signals
  - **Velocity (40%)**: 참여 증가 속도
  - **Volume (30%)**: 게시물 수량 임계값 충족
  - **Amplification (30%)**: 크로스 플랫폼 확산(부스트 적용)
- **Detect** whether content looks **Organic** or **Paid/Promoted**
- **Export** analysis results to JSON under `output/`

## Quickstart

### Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

(개발용)

```bash
pip install -e ".[dev]"
```

### Run (Demo mode)

Demo 모드는 API 키 없이도 동작하며, 트렌드 감지 로직을 빠르게 확인할 때 유용합니다.

실제 API로 실행하려면 `.env`를 설정한 뒤 `--demo` 없이 실행하세요.

```bash
trend-analyzer "fashion" --demo --limit 30
trend-analyzer "fashion" --demo --limit 30 --export json
```

또는 모듈로 실행:

```bash
python -m trend_analyzer "fashion" --demo --limit 30
```

## Configuration (.env)

`.env.example`을 복사해 `.env`를 만들고 값을 채워 넣으세요.

```bash
cp .env.example .env
```

필수/옵션 환경변수:

- **`META_ACCESS_TOKEN`**: Meta 앱 액세스 토큰 (없으면 Demo 모드로 자동 전환)
- **`INSTAGRAM_BUSINESS_ACCOUNT_ID`**: Instagram 해시태그 검색에 필요
- **`THREADS_USER_ID`**: Threads 사용자 ID (현재 CLI 수집 흐름에서는 미사용)
- **`TREND_VELOCITY_WINDOW_HOURS`**: velocity 계산 시간 창(기본 6)
- **`TREND_VOLUME_THRESHOLD`**: 최소 게시물 수(기본 10)
- **`CROSS_PLATFORM_BOOST`**: 크로스 플랫폼 부스트(기본 1.5)

### Notes on API requirements

- Instagram Graph API 해시태그 검색은 **App Review / 권한**이 필요할 수 있습니다.
- Threads 키워드 검색은 `threads_keyword_search` 권한이 필요하며, 현재 `src/trend_analyzer/main.py`에서는 권한 이슈로 Threads 수집이 주석 처리되어 있습니다.

## Output

`--export json` 옵션을 사용하면 결과가 `output/` 폴더에 저장됩니다. (`output/` 및 `*.json`은 기본적으로 `.gitignore`에 의해 커밋에서 제외됩니다.)

- **파일명 형식**: `output/trend_<topic>_<YYYYMMDD_HHMMSS>.json`
- **주요 필드**:
  - `topic`
  - `trend_score`, `velocity_score`, `volume_score`, `amplification_score`
  - `trend_level` (예: `"🔥 HOT TREND"`, `"⚡ TRENDING"`)
  - `total_posts`, `threads_count`, `instagram_count`, `is_cross_platform`
  - `organic_count`, `paid_count`, `uncertain_count`, `dominant_promotion_label`, `organic_ratio`
  - `top_posts` (참여도 상위 게시물 최대 5개)

## Project structure

- `src/trend_analyzer/main.py`: CLI entrypoint (`trend-analyzer`)
- `src/trend_analyzer/config.py`: `.env`/환경변수 로딩 (Pydantic Settings)
- `src/trend_analyzer/scrapers/`: 플랫폼 수집기
  - `instagram_scraper.py`: Instagram Graph API
  - `threads_scraper.py`: Threads API
  - `base.py`: `BaseScraper`, `DemoScraper`
- `src/trend_analyzer/analyzer/`: 분석 로직
  - `trend_detector.py`: 트렌드 스코어링
  - `promotion_detector.py`: Organic vs Paid 신호
- `tests/`: pytest 테스트

## Development

### Run tests

```bash
pytest
```

## Security

- **Never commit** secrets in `.env`.
- 이 저장소에 이미 `.env`가 추적(tracked)된 상태라면, Git에서 제거하고 로컬에서만 사용하세요:

```bash
git rm --cached .env
```

## Docs

- `PRD.md`: 제품 요구사항 문서(드래프트). 현재 구현은 Meta(Threads/Instagram) 중심의 MVP에 해당합니다.
