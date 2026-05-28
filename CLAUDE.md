AI 기반 암호화폐 트레이딩 시스템 개발 문서 (Draft v0.1)

1. 프로젝트 개요

프로젝트명

AI Assisted Crypto Trading System

목표

뉴스, 경제 지표, 시장 데이터 등을 종합적으로 분석하여 자동 또는 반자동으로 암호화폐 매매를 수행하는 개인용 트레이딩 시스템 구축.

핵심 컨셉

* OpenClaw가 외부 데이터를 수집하고 분석 요청 수행
* Python 서버가 점수 계산 및 최종 트레이딩 로직 수행
* Hugging Face 모델을 활용한 뉴스/감성 분석
* Bybit API를 이용한 실제 거래
* Docker 기반 로컬 환경 운영
* 사람의 최종 승인 또는 조건부 자동 매매

⸻

2. 시스템 아키텍처

전체 구조

[뉴스/RSS/API/CPI 데이터]
            ↓
        OpenClaw
            ↓
    데이터 정리 및 요약
            ↓
      Python FastAPI
            ↓
    HuggingFace Model
            ↓
      점수 계산 엔진
            ↓
 ┌───────────────┐
 │ 점수 < 10     │ → 무시
 │ 10~19         │ → 사용자 알림
 │ 20 이상       │ → 자동 매수/매도
 └───────────────┘
            ↓
        Bybit API
            ↓
       거래 결과 저장
            ↓
     OpenClaw 알림 전송
            ↓
        모바일 알림

⸻

3. 기술 스택

Backend

* Python 3.12
* FastAPI
* Uvicorn

AI / ML

* Ollama
* Hugging Face Transformers
* FinBERT
* DistilRoBERTa Financial Sentiment

데이터 처리

* Pandas
* NumPy

백테스팅

* Backtrader
* vectorbt (선택)

저장소

* SQLite
* TinyDB (후보)
* JSON File Storage

인프라

* Docker
* Docker Compose

거래소 API

* Bybit API

알림

* OpenClaw Message
* Telegram (후보)
* Discord Webhook (후보)

⸻

4. 핵심 기능

4.1 뉴스 수집

역할

* RSS 수집
* 뉴스 API 호출
* 경제 지표 수집(CPI, 금리 등)

담당

OpenClaw

수집 대상 예시

* CoinDesk
* CoinTelegraph
* Binance News
* Fed CPI 발표
* Fear & Greed Index

⸻

4.2 뉴스 감성 분석

역할

뉴스가 시장에 긍정/부정 영향을 줄지 분석

모델

* FinBERT
* DistilRoBERTa

출력 예시

{
  "title": "Bitcoin ETF approved",
  "sentiment": "positive",
  "score": 0.91
}

⸻

4.3 시장 지표 분석

사용 예정 지표

지표	목적
ATR	변동성
RSI	과매수/과매도
MACD	추세
EMA/SMA	이동 평균
볼린저 밴드	변동성 수축/폭발
거래량 변화율	시장 관심도
Fear & Greed	심리 상태

⸻

5. 점수 계산 시스템

개념

각 지표와 뉴스 분석 결과를 점수화하여 최종 매매 여부 결정.

⸻

예시

항목	조건	점수
뉴스 감성	매우 긍정	+5
RSI	과매도	+3
거래량 증가	150% 이상	+4
MACD 골든크로스	발생	+5
CPI 악화	발생	-7

⸻

최종 규칙

점수	행동
0~9	무시
10~19	사용자 승인 요청
20 이상	자동 거래

⸻

6. 거래 전략

초기 전략

추세 추종 + 뉴스 필터 전략

상승 추세
+
긍정 뉴스
+
거래량 증가
=
매수 후보

⸻

향후 추가 예정

* Mean Reversion
* Volatility Breakout
* Reinforcement Learning
* Portfolio Rebalancing

⸻

7. FastAPI 서버 구조

예상 구조

/app
 ├── main.py
 ├── api/
 ├── services/
 ├── models/
 ├── indicators/
 ├── backtest/
 ├── traders/
 ├── database/
 ├── logs/
 └── utils/

⸻

8. API 설계

뉴스 분석 요청

POST /analyze

{
  "news": [
    {
      "title": "Bitcoin surges",
      "content": "..."
    }
  ]
}

⸻

응답

{
  "score": 17,
  "action": "notify"
}

⸻

9. 로그 시스템

목적

* 추후 디버깅
* 백테스팅 검증
* 거래 원인 분석
* AI 판단 추적

⸻

저장 대상

로그 종류	설명
API 호출	OpenClaw ↔ Python
뉴스 원문	분석 데이터
AI 분석 결과	sentiment
최종 점수	score
거래 결과	buy/sell
오류 로그	exception

⸻

10. 백테스팅 시스템

목표

과거 데이터를 이용해 전략 검증.

⸻

검증 항목

항목	의미
수익률	Total Return
MDD	최대 낙폭
승률	Win Rate
샤프 비율	Risk 대비 수익
거래 횟수	과매매 여부

⸻

데이터 소스

* Bybit Historical Data
* Binance Kline Data
* CSV 저장 데이터

⸻

11. Docker 구성

구성 요소

Container 1

OpenClaw

Container 2

Ollama

Container 3

Python FastAPI

Container 4 (선택)

Monitoring / Grafana

⸻

Docker Compose 예시 구조

services:
  openclaw:
    ...
  ollama:
    ...
  trading-api:
    ...
  sqlite:
    ...

⸻

12. 개발 우선순위

Phase 1

* Docker 환경 구축
* FastAPI 생성
* Bybit API 연동

⸻

Phase 2

* RSS 수집
* 뉴스 분석
* 점수 계산

⸻

Phase 3

* 백테스팅
* 알림 시스템

⸻

Phase 4

* 자동 거래
* 리스크 관리
* 최적화

⸻

13. 리스크 관리

필수 제한사항

항목	제한
최대 손실	일일 -3%
최대 포지션	총 자산의 10%
연속 손실 제한	5회
레버리지	초기엔 사용 금지

⸻

14. 현재 설계의 장점

* 구조가 단순함
* 유지보수가 쉬움
* Docker 기반이라 재현 가능
* AI 역할과 거래 역할 분리
* 개인 프로젝트 규모에 적합

⸻

15. 현재 설계의 위험 요소

1. 과적합 위험

백테스트 성능 ≠ 실제 수익

2. 뉴스 신뢰도 문제

가짜 뉴스 가능성 존재

3. LLM 환각 문제

AI가 잘못 판단 가능

4. 시장 급변 리스크

알고리즘이 대응 못할 수 있음

5. API 장애

거래소 응답 실패 가능

⸻

16. 추천 개발 방향

현재 단계에서는:

* “완벽한 AI 트레이더”를 목표로 하지 말 것
* “안전한 실험 플랫폼”을 목표로 할 것
* 자동매매보다 “의사결정 보조 시스템”으로 시작할 것

추천 흐름:

데이터 수집
→ 분석
→ 점수 계산
→ 사용자 승인
→ 거래

초기에는 완전자동보다 반자동 시스템이 훨씬 안전하고 현실적임.
