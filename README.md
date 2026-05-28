# AI Crypto Trading System

뉴스 감성 분석 + 기술적 지표를 결합한 암호화폐 반자동/자동 트레이딩 시스템.

FinBERT로 뉴스를 분석하고, Bybit 시장 데이터(RSI · MACD · 볼린저 밴드)와 결합해 점수를 계산합니다.  
점수에 따라 **무시 → 사용자 승인 요청 → 자동 주문** 세 단계로 매매를 결정합니다.

---

## 아키텍처

```
[뉴스 / RSS / CPI / Fear&Greed]
            ↓
        OpenClaw  (데이터 수집)
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
  ┌─────────────────────┐
  │ |score| < 10  → 무시 │
  │ 10 ~ 19  → 사용자 알림│
  │ 20 이상  → 자동 주문  │
  └─────────────────────┘
            ↓
        Bybit API
            ↓
       SQLite 로그 저장
```

---

## 주요 기능

| 기능 | 설명 |
|---|---|
| 뉴스 감성 분석 | ProsusAI/FinBERT 모델로 긍정 · 부정 · 중립 판별 |
| 기술적 지표 | RSI · MACD · 볼린저밴드 · 거래량 변화율 |
| 점수 시스템 | 지표별 가중치 합산 → 매매 행동 결정 |
| Bybit 연동 | Spot Market 주문 · 잔고 조회 · Testnet 지원 |
| 리스크 관리 | 포지션 한도 · 일일 손실 제한 · 레버리지 금지 |
| Mock 모드 | API 키·ML 모델 없이 전체 파이프라인 테스트 |
| 로그 기록 | 분석 이력 · 거래 이력 SQLite 자동 저장 |

---

## 빠른 시작

### 1. 환경변수 설정

```bash
cp .env.example .env
```

```env
# Mock 모드로 먼저 실행 (API 키 없이 테스트)
MOCK_MODE=true
MOCK_SCENARIO=bullish   # default | bullish | bearish

# 실거래 전환 시 아래 값 입력
BYBIT_API_KEY=your_api_key
BYBIT_API_SECRET=your_api_secret
BYBIT_TESTNET=true
```

### 2. Docker로 실행

```bash
# Mock 모드 (경량, 빠름)
docker compose -f docker-compose.mock.yml up --build

# 전체 모드 (FinBERT 모델 포함, 수 GB 다운로드)
docker compose up --build
```

### 3. API 문서 확인

```
http://localhost:8000/docs
```

---

## API

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

### 기타 엔드포인트

| Method | Endpoint | 설명 |
|---|---|---|
| `GET` | `/api/v1/market/{symbol}` | 시장 데이터 + 기술적 지표 조회 |
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
|score| 0 ~ 9   → IGNORE    (무시)
|score| 10 ~ 19 → NOTIFY    (사용자 승인 요청)
|score| 20+     → AUTO_TRADE (자동 주문 실행)
```

---

## 리스크 관리

```env
MAX_DAILY_LOSS_PCT=3.0      # 일일 최대 손실 -3%
MAX_POSITION_PCT=10.0       # 포지션 최대 자산의 10%
MAX_CONSECUTIVE_LOSSES=5    # 연속 손실 5회 시 중지
# 레버리지 사용 금지 (초기 단계)
```

---

## 프로젝트 구조

```
ai_trading/
├── docker-compose.yml          # 전체 환경 (ollama 포함)
├── docker-compose.mock.yml     # Mock 경량 환경
├── .env.example
└── app/
    ├── main.py                 # FastAPI 진입점
    ├── Dockerfile
    ├── requirements.txt        # 전체 의존성 (transformers, pybit 등)
    ├── requirements-mock.txt   # Mock용 경량 의존성
    ├── api/
    │   └── routes.py           # API 엔드포인트
    ├── models/
    │   └── schemas.py          # Pydantic 스키마
    ├── services/
    │   ├── sentiment.py        # FinBERT 감성 분석
    │   ├── market.py           # Bybit 시장 데이터 + 지표
    │   └── scoring.py          # 점수 계산 + 행동 결정
    ├── traders/
    │   └── bybit_trader.py     # 주문 실행 + 리스크 체크
    ├── database/
    │   └── db.py               # SQLite (분석/거래 로그)
    ├── utils/
    │   └── mock.py             # Mock 데이터 생성기
    ├── indicators/             # (Phase 2 확장 예정)
    └── backtest/               # (Phase 3 구현 예정)
```

---

## 개발 로드맵

- [x] **Phase 1** — FastAPI · Bybit API · 감성 분석 · 점수 엔진 · Mock 시스템 · Docker
- [ ] **Phase 2** — RSS 자동 수집 · 분석 스케줄러 · Fear&Greed API · OpenClaw 웹훅
- [ ] **Phase 3** — 알림 시스템 (Telegram/Discord) · 백테스팅 · Testnet 실거래 검증
- [ ] **Phase 4** — 동적 수량 계산 · 연속손실 추적 · 모니터링 대시보드

---

## 기술 스택

- **Backend** — Python 3.12 · FastAPI · Uvicorn · SQLAlchemy
- **AI / ML** — FinBERT (ProsusAI/finbert) · HuggingFace Transformers
- **데이터** — pandas · pandas-ta · numpy
- **거래소** — Bybit Unified Trading API (pybit)
- **인프라** — Docker · Docker Compose · SQLite

---

## 주의사항

이 시스템은 **개인 실험 목적**으로 제작됐습니다.

- 백테스트 성능 ≠ 실제 수익
- AI 모델의 판단 오류 가능성 존재
- 실거래 전 반드시 Testnet에서 충분히 검증
- 자동 매매보다 **반자동 (사용자 승인)** 모드로 시작 권장
