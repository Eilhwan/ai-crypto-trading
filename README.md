# AI Crypto Trading System

뉴스 감성 분석 + 기술적 지표를 결합한 암호화폐 반자동/자동 트레이딩 시스템.

FinBERT로 뉴스를 분석하고, Bybit 시장 데이터(RSI · MACD · 볼린저 밴드)와 결합해 점수를 계산합니다.  
점수에 따라 **무시 → 사용자 승인 요청 → 자동 주문** 세 단계로 매매를 결정합니다.

---

## 목차

1. [아키텍처](#아키텍처)
2. [주요 기능](#주요-기능)
3. [온보딩 — 처음 시작하기](#온보딩--처음-시작하기)
4. [테스트](#테스트)
5. [실제 사용법](#실제-사용법)
6. [알림 설정](#알림-설정)
7. [API 레퍼런스](#api-레퍼런스)
8. [점수 시스템](#점수-시스템)
9. [리스크 관리](#리스크-관리)
10. [프로젝트 구조](#프로젝트-구조)
11. [개발 로드맵](#개발-로드맵)

---

## 아키텍처

```
[뉴스 / RSS / CPI / Fear&Greed]
            ↓
   자동 RSS 수집 (APScheduler)
   또는 POST /webhook/news
            ↓
    POST /api/v1/analyze
            ↓
    FinBERT 감성 분석
            ↓
    기술적 지표 (Bybit Kline)
    RSI · MACD · 볼린저밴드 · 거래량
            ↓
       점수 계산 엔진
            ↓
  ┌─────────────────────────┐
  │ |score| < 10  → 무시    │
  │ 10 ~ 19  → 알림 전송    │
  │ 20 이상  → 자동 주문    │
  └─────────────────────────┘
            ↓
        Bybit API
            ↓
       SQLite 로그 저장
            ↓
  OpenClaw · Telegram · Discord 알림
```

---

## 주요 기능

| 기능 | 설명 |
|---|---|
| 뉴스 감성 분석 | ProsusAI/FinBERT 모델로 긍정·부정·중립 판별 |
| RSS 자동 수집 | CoinDesk · CoinTelegraph 등 주기적 수집 (설정 가능) |
| 기술적 지표 | RSI · MACD · 볼린저밴드 · 거래량 변화율 |
| Fear & Greed | Alternative.me API 실시간 연동 |
| 점수 시스템 | 지표별 가중치 합산 → 매매 행동 결정 |
| 자동 스케줄러 | 설정된 간격마다 뉴스 수집 + 분석 자동 실행 |
| 백테스팅 | 과거 캔들 데이터로 전략 수익률·MDD·샤프 비율 검증 |
| Bybit 연동 | Spot Market 주문 · 잔고 조회 · Testnet 지원 |
| 리스크 관리 | 포지션 한도 · 일일 손실 제한 · 레버리지 금지 |
| 알림 채널 | OpenClaw · Telegram · Discord Webhook 동시 발송 |
| Mock 모드 | API 키·ML 모델 없이 전체 파이프라인 테스트 |
| 로그 기록 | 분석 이력 · 거래 이력 · 백테스트 이력 SQLite 저장 |

---

## 온보딩 — 처음 시작하기

### 사전 요구사항

- Docker Desktop 4.x 이상 (실행 중 상태)
- Git

### Step 1 — 저장소 클론 및 환경변수 설정

```bash
git clone <repo-url>
cd ai_trading

cp .env.example .env
```

`.env`는 처음에 **Mock 모드** 기본값으로 채워져 있습니다. API 키 없이 바로 실행 가능합니다.

```env
MOCK_MODE=true
MOCK_SCENARIO=bullish   # default | bullish | bearish
```

### Step 2 — Mock 모드로 첫 실행

```bash
chmod +x start.sh
./start.sh              # 기본값: mock 모드
```

또는 직접 Docker Compose로:

```bash
docker compose -f docker-compose.mock.yml up --build
```

정상 시작되면 아래 출력이 나타납니다.

```
● trading-api-mock  Up (healthy)  0.0.0.0:8000->8000/tcp

엔드포인트
  http://localhost:8000          Trading API
  http://localhost:8000/docs     Swagger UI
```

### Step 3 — 첫 번째 API 호출

```bash
# 헬스체크
curl -s http://localhost:8000/api/v1/health

# 뉴스 분석 (bullish 시나리오 모의 데이터)
curl -s -X POST http://localhost:8000/api/v1/analyze \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"BTCUSDT","news":[{"title":"Bitcoin ETF approved by SEC"}]}' \
  | python3 -m json.tool
```

### Step 4 — Swagger UI 확인

브라우저에서 `http://localhost:8000/docs` 를 열어 모든 엔드포인트를 인터랙티브하게 테스트할 수 있습니다.

---

## 테스트

### Mock 시나리오 변경

`.env`의 `MOCK_SCENARIO` 값을 바꾸고 재시작하면 다른 시장 상황을 시뮬레이션합니다.

| 시나리오 | RSI | MACD | 볼린저 | 예상 점수 |
|---|---|---|---|---|
| `default` | 중립 | 중립 | 중립 | ~0 |
| `bullish` | 과매도 | 골든크로스 | 하단 | +20 이상 (자동 거래) |
| `bearish` | 과매수 | 데스크로스 | 상단 | -20 이하 (자동 매도) |

```bash
# .env 수정 후
MOCK_SCENARIO=bearish

# 재시작
./start.sh restart
```

### 핵심 API 테스트 모음

**1. 헬스체크**
```bash
curl -s http://localhost:8000/api/v1/health
```

**2. 뉴스 분석 — 긍정 뉴스**
```bash
curl -s -X POST http://localhost:8000/api/v1/analyze \
  -H 'Content-Type: application/json' \
  -d '{
    "symbol": "BTCUSDT",
    "fear_greed_index": 15,
    "news": [
      {"title": "Bitcoin ETF approved by SEC", "content": "Institutional adoption surge expected"},
      {"title": "Fed signals rate cut", "content": "Risk assets rally on dovish outlook"}
    ]
  }' | python3 -m json.tool
```

**3. 뉴스 분석 — 부정 뉴스**
```bash
curl -s -X POST http://localhost:8000/api/v1/analyze \
  -H 'Content-Type: application/json' \
  -d '{
    "symbol": "BTCUSDT",
    "fear_greed_index": 85,
    "news": [
      {"title": "SEC rejects Bitcoin ETF again"},
      {"title": "Major exchange hacked, $500M lost"}
    ]
  }' | python3 -m json.tool
```

**4. 시장 데이터 + 기술적 지표 조회**
```bash
curl -s http://localhost:8000/api/v1/market/BTCUSDT | python3 -m json.tool
```

**5. Fear & Greed 지수 조회**
```bash
curl -s http://localhost:8000/api/v1/fear-greed | python3 -m json.tool
```

**6. 스케줄러 상태 확인**
```bash
curl -s http://localhost:8000/api/v1/scheduler/status | python3 -m json.tool
```

**7. 스케줄러 수동 실행**
```bash
curl -s -X POST http://localhost:8000/api/v1/scheduler/trigger
```

**8. 분석 로그 조회**
```bash
curl -s "http://localhost:8000/api/v1/logs/analysis?limit=5" | python3 -m json.tool
```

**9. 거래 로그 조회**
```bash
curl -s "http://localhost:8000/api/v1/logs/trades?limit=5" | python3 -m json.tool
```

### 백테스팅 테스트

```bash
curl -s -X POST http://localhost:8000/api/v1/backtest/run \
  -H 'Content-Type: application/json' \
  -d '{
    "symbol": "BTCUSDT",
    "days": 30,
    "interval": "240",
    "initial_capital": 1000.0,
    "news_score": 3.0,
    "fear_greed": 40.0,
    "position_pct": 10.0,
    "entry_score": 10.0,
    "exit_score": -5.0
  }' | python3 -m json.tool
```

응답 예시:
```json
{
  "symbol": "BTCUSDT",
  "days": 30,
  "initial_capital": 1000.0,
  "final_capital": 1087.43,
  "total_return_pct": 8.74,
  "max_drawdown_pct": 4.21,
  "win_rate": 62.5,
  "sharpe_ratio": 1.34,
  "total_trades": 8,
  "candles_analyzed": 177
}
```

### 백테스팅 파라미터 설명

| 파라미터 | 설명 | 기본값 |
|---|---|---|
| `interval` | 캔들 단위: `60`(1h) · `120`(2h) · `240`(4h) · `D`(일봉) | `240` |
| `days` | 백테스트 기간 (일) | `30` |
| `initial_capital` | 시작 자본 (USDT) | `1000` |
| `news_score` | 고정 뉴스 점수 (실제 뉴스 없이 시뮬레이션) | `0` |
| `position_pct` | 진입 시 자본 대비 투자 비율 (%) | `10` |
| `entry_score` | 매수 진입 임계 점수 | `10` |
| `exit_score` | 매도 청산 임계 점수 | `-5` |

### 로그 실시간 확인

```bash
./start.sh logs
# 또는
docker logs -f trading-api-mock
```

---

## 실제 사용법

### Step 1 — Bybit Testnet 설정

실거래 전 반드시 Testnet에서 충분히 검증합니다.

1. [Bybit Testnet](https://testnet.bybit.com) 가입
2. API 키 발급 (Read + Trade 권한)
3. `.env` 수정:

```env
MOCK_MODE=false
BYBIT_API_KEY=your_testnet_api_key
BYBIT_API_SECRET=your_testnet_api_secret
BYBIT_TESTNET=true
```

4. Full 모드로 실행:

```bash
./start.sh up --full
```

> Full 모드는 FinBERT 모델을 다운로드합니다 (초기 수 GB, 수 분 소요).

### Step 2 — 감시 심볼 및 스케줄 설정

```env
WATCH_SYMBOLS=BTCUSDT,ETHUSDT   # 감시할 심볼 (쉼표 구분)
SCHEDULE_INTERVAL_MIN=30         # 분석 주기 (분)
NEWS_LOOKBACK_HOURS=2            # 수집할 뉴스 범위 (시간)
```

스케줄러는 서버 시작 시 자동으로 활성화됩니다. 수동으로 즉시 실행하려면:

```bash
curl -s -X POST http://localhost:8000/api/v1/scheduler/trigger
```

### Step 3 — 웹훅으로 외부 뉴스 수신

외부 시스템(OpenClaw 등)에서 뉴스를 직접 전달할 수 있습니다.

`.env`에 웹훅 토큰 설정:
```env
WEBHOOK_TOKEN=your_secure_token_here
```

뉴스 전송:
```bash
curl -s -X POST http://localhost:8000/api/v1/webhook/news \
  -H 'Content-Type: application/json' \
  -d '{
    "token": "your_secure_token_here",
    "symbol": "BTCUSDT",
    "news": [
      {"title": "Bitcoin breaks $100k", "content": "..."}
    ]
  }'
```

### Step 4 — 점수 임계값 조정

초기에는 자동 거래 임계값을 높게 설정해 **사람이 승인하는 반자동 모드**로 운영하는 것을 권장합니다.

```env
SCORE_NOTIFY_MIN=10      # 이 점수 이상이면 알림 발송
SCORE_AUTO_TRADE_MIN=20  # 이 점수 이상이면 자동 주문 (높을수록 보수적)
```

| 행동 | 설명 |
|---|---|
| `ignore` | 점수 < SCORE_NOTIFY_MIN → 무시 |
| `notify` | SCORE_NOTIFY_MIN ≤ 점수 < SCORE_AUTO_TRADE_MIN → 알림만 발송 |
| `auto_trade` | 점수 ≥ SCORE_AUTO_TRADE_MIN → 자동 주문 실행 |

### Step 5 — 실거래 전환

Testnet 검증 완료 후:

```env
BYBIT_TESTNET=false
BYBIT_API_KEY=your_mainnet_api_key
BYBIT_API_SECRET=your_mainnet_api_secret
```

---

## 알림 설정

점수가 임계값을 넘으면 설정된 채널로 동시에 알림이 발송됩니다.

### Telegram

1. [@BotFather](https://t.me/BotFather)에서 봇 생성 → 토큰 발급
2. 봇에게 메시지를 보낸 후 Chat ID 확인:
   ```bash
   curl https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
3. `.env` 설정:
   ```env
   TELEGRAM_BOT_TOKEN=123456789:AAxxxxxx
   TELEGRAM_CHAT_ID=987654321
   ```

### Discord Webhook

1. Discord 서버 설정 → 연동 → 웹훅 → URL 복사
2. `.env` 설정:
   ```env
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxx/yyy
   ```

### OpenClaw

```env
OPENCLAW_URL=http://host.docker.internal:18789
OPENCLAW_TOKEN=your_openclaw_token
```

세 채널은 독립적으로 동작합니다. 미설정 채널은 자동으로 건너뜁니다.

---

## API 레퍼런스

### `POST /api/v1/analyze`

뉴스 분석 → 점수 계산 → 필요 시 자동 주문 실행

**요청**
```json
{
  "symbol": "BTCUSDT",
  "fear_greed_index": 20,
  "news": [
    {
      "title": "Bitcoin ETF approved by SEC",
      "content": "Major institutional adoption expected..."
    }
  ]
}
```

**응답**
```json
{
  "symbol": "BTCUSDT",
  "score": 20.59,
  "action": "auto_trade",
  "breakdown": {
    "news_score": 6.59,
    "rsi_score": 3.0,
    "macd_score": 5.0,
    "volume_score": 4.0,
    "fear_greed_score": 2.0,
    "total": 20.59
  },
  "sentiments": [
    {
      "title": "Bitcoin ETF approved by SEC",
      "sentiment": "positive",
      "score": 0.97,
      "confidence": 0.97
    }
  ],
  "reasoning": "총점: 20.6 (매수 신호) | 뉴스 감성: +6.6 | RSI: +3.0 | MACD: +5.0 | 거래량: +4.0 | 공포/탐욕: +2.0 | → 자동 거래 실행"
}
```

### 전체 엔드포인트

| Method | Endpoint | 설명 |
|---|---|---|
| `POST` | `/api/v1/analyze` | 뉴스 분석 + 점수 계산 + 자동 거래 |
| `POST` | `/api/v1/webhook/news` | 외부 시스템 뉴스 수신 (토큰 인증) |
| `GET` | `/api/v1/fear-greed` | Fear & Greed 지수 조회 |
| `GET` | `/api/v1/scheduler/status` | 스케줄러 상태 및 다음 실행 시각 |
| `POST` | `/api/v1/scheduler/trigger` | 스케줄러 수동 즉시 실행 |
| `POST` | `/api/v1/backtest/run` | 백테스팅 실행 |
| `GET` | `/api/v1/backtest/results` | 백테스트 이력 조회 |
| `GET` | `/api/v1/market/{symbol}` | 시장 데이터 + 기술적 지표 |
| `POST` | `/api/v1/trade/manual` | 수동 매수/매도 주문 |
| `GET` | `/api/v1/logs/analysis` | 분석 이력 조회 |
| `GET` | `/api/v1/logs/trades` | 거래 이력 조회 |
| `GET` | `/api/v1/health` | 서버 상태 확인 |

---

## 점수 시스템

점수의 절댓값으로 행동을 결정합니다. 양수 = 매수 신호, 음수 = 매도 신호.

| 지표 | 조건 | 점수 |
|---|---|---|
| 뉴스 감성 | 매우 긍정 | 최대 +7 |
| 뉴스 감성 | 매우 부정 | 최소 -7 |
| RSI | 과매도 (< 30) | +3 |
| RSI | 과매수 (> 70) | -3 |
| MACD | 골든크로스 | +5 |
| MACD | 데스크로스 | -5 |
| 거래량 | 평균 대비 +150% 이상 | +4 |
| 거래량 | 평균 대비 +50~150% | +2 |
| 거래량 | 평균 대비 -50% 이하 | -2 |
| 공포/탐욕 | 극도의 공포 (< 25) | +2 |
| 공포/탐욕 | 극도의 탐욕 (> 75) | -2 |

**임계값 (`.env`에서 조정 가능)**

```
|score| 0 ~ 9   → IGNORE     (무시)
|score| 10 ~ 19 → NOTIFY     (알림 발송)
|score| 20+     → AUTO_TRADE (자동 주문 실행)
```

---

## 리스크 관리

```env
MAX_DAILY_LOSS_PCT=3.0       # 일일 최대 손실 -3%
MAX_POSITION_PCT=10.0        # 포지션 최대 자산의 10%
MAX_CONSECUTIVE_LOSSES=5     # 연속 손실 5회 시 거래 중단
# 레버리지 사용 금지 (초기 단계)
```

---

## start.sh 커맨드

```bash
./start.sh [COMMAND] [--mock|--full]

# Commands
up        서비스 시작 (기본값: mock 모드)
down      서비스 중지
restart   서비스 재시작
status    컨테이너 상태 + 엔드포인트 출력
logs      로그 스트리밍
pull      Ollama 모델 다운로드 (full 모드 전용)

# 예시
./start.sh                   # mock 모드로 시작
./start.sh up --full         # full 모드로 시작 (FinBERT + 실 Bybit)
./start.sh down              # 중지
./start.sh logs              # 실시간 로그
./start.sh status            # 상태 확인
```

---

## 프로젝트 구조

```
ai_trading/
├── start.sh                    # 통합 시작/중지 스크립트
├── docker-compose.yml          # 전체 환경 (FinBERT + Ollama)
├── docker-compose.mock.yml     # Mock 경량 환경
├── .env.example
└── app/
    ├── main.py                 # FastAPI 진입점 + 스케줄러 초기화
    ├── Dockerfile
    ├── requirements.txt        # 전체 의존성 (transformers, pybit 등)
    ├── requirements-mock.txt   # Mock용 경량 의존성
    ├── api/
    │   └── routes.py           # 모든 API 엔드포인트
    ├── models/
    │   └── schemas.py          # Pydantic 스키마
    ├── services/
    │   ├── sentiment.py        # FinBERT 감성 분석
    │   ├── market.py           # Bybit 시장 데이터 + 지표
    │   ├── scoring.py          # 점수 계산 + 행동 결정
    │   ├── scheduler.py        # APScheduler 자동 분석 사이클
    │   ├── news_collector.py   # RSS 수집 + 중복 제거
    │   ├── fear_greed.py       # Alternative.me Fear & Greed API
    │   └── notifier.py         # OpenClaw · Telegram · Discord 알림
    ├── traders/
    │   └── bybit_trader.py     # 주문 실행 + 리스크 체크
    ├── backtest/
    │   └── engine.py           # 백테스팅 엔진 (수익률·MDD·샤프)
    ├── database/
    │   └── db.py               # SQLite (분석/거래/백테스트 로그)
    ├── utils/
    │   └── mock.py             # Mock 데이터 생성기
    ├── data/
    │   └── trading.db          # SQLite 데이터베이스 파일
    └── logs/
        └── trading.log         # 애플리케이션 로그
```

---

## 개발 로드맵

- [x] **Phase 1** — FastAPI · Bybit API · FinBERT 감성 분석 · 점수 엔진 · Mock 시스템 · Docker
- [x] **Phase 2** — RSS 자동 수집 · APScheduler · Fear&Greed API · Webhook · OpenClaw 연동
- [x] **Phase 3** — 백테스팅 엔진 · Telegram/Discord 알림 · 멀티채널 노티파이어
- [ ] **Phase 4** — 동적 수량 계산 · 연속손실 실시간 추적 · 모니터링 대시보드

---

## 기술 스택

- **Backend** — Python 3.12 · FastAPI · Uvicorn · SQLAlchemy
- **AI / ML** — FinBERT (ProsusAI/finbert) · HuggingFace Transformers
- **스케줄링** — APScheduler (AsyncIOScheduler)
- **데이터** — pandas · pandas-ta · numpy
- **뉴스 수집** — feedparser (RSS)
- **거래소** — Bybit Unified Trading API (pybit)
- **인프라** — Docker · Docker Compose · SQLite

---

## 주의사항

이 시스템은 **개인 실험 목적**으로 제작됐습니다.

- 백테스트 성능 ≠ 실제 수익
- AI 모델의 판단 오류 가능성 존재
- 실거래 전 반드시 Testnet에서 충분히 검증
- 자동 매매보다 **반자동 (SCORE_AUTO_TRADE_MIN 높게 설정)** 모드로 시작 권장
