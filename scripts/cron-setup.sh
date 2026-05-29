#!/usr/bin/env bash
# AI Trading × OpenClaw — cron 등록 스크립트
# 사용법: ./scripts/cron-setup.sh [--dry-run]
#
# ┌─ 동작 방식 ──────────────────────────────────────────────────────────────┐
# │  GOOGLE_API_KEY 또는 OPENAI_API_KEY 설정 시:                             │
# │    --message --tools exec  → Gemini/GPT 에이전트가 curl 직접 실행        │
# │  미설정 시:                                                               │
# │    --system-event  → 모니터링 이벤트 전용                                │
# │    (자동화는 trading-api 내부 APScheduler 30분 간격으로 처리)             │
# └─────────────────────────────────────────────────────────────────────────┘
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# ── 사전 점검 ────────────────────────────────────────────────────────────────
if ! docker ps --format '{{.Names}}' | grep -q '^openclaw-gateway$'; then
  error "openclaw-gateway 컨테이너가 실행 중이지 않습니다. './start.sh' 먼저 실행하세요."
fi

TRADING_API_CONTAINER=$(docker ps --format '{{.Names}}' | grep '^trading-api' | head -1 || true)
if [[ -z "$TRADING_API_CONTAINER" ]]; then
  error "trading-api 컨테이너가 실행 중이지 않습니다."
fi
API_URL="http://${TRADING_API_CONTAINER}:8000"
info "Trading API: ${TRADING_API_CONTAINER} → ${API_URL}"

# .env에서 값 읽기
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEBHOOK_TOKEN="your_webhook_token_here"
HAS_MODEL=false
MODEL_PROVIDER="(없음)"

if [[ -f "$SCRIPT_DIR/.env" ]]; then
  wt=$(grep '^WEBHOOK_TOKEN=' "$SCRIPT_DIR/.env" | cut -d= -f2 | tr -d '"' | tr -d "'" || true)
  [[ -n "$wt" && "$wt" != "change_this"* ]] && WEBHOOK_TOKEN="$wt"

  g_key=$(grep '^GOOGLE_API_KEY=' "$SCRIPT_DIR/.env" | cut -d= -f2 | tr -d '"' | tr -d "'" || true)
  ok_key=$(grep '^OPENAI_API_KEY=' "$SCRIPT_DIR/.env" | cut -d= -f2 | tr -d '"' | tr -d "'" || true)

  if [[ -n "$g_key" && ${#g_key} -gt 10 ]]; then
    HAS_MODEL=true; MODEL_PROVIDER="Google Gemini (GOOGLE_API_KEY)"
  elif [[ -n "$ok_key" && "$ok_key" != "your"* && ${#ok_key} -gt 10 ]]; then
    HAS_MODEL=true; MODEL_PROVIDER="OpenAI (OPENAI_API_KEY)"
  fi
fi

[[ "$WEBHOOK_TOKEN" == "your_webhook_token_here" ]] && \
  warn "WEBHOOK_TOKEN 미설정 — .env 에서 WEBHOOK_TOKEN을 설정하세요."

OC="docker exec openclaw-gateway node dist/index.js"

# ── cron 등록 헬퍼 ──────────────────────────────────────────────────────────
# 에이전트 모드: --message --tools exec
# 모니터링 모드: --system-event
add_exec_cron_every() {
  local name="$1" every="$2" cmd="$3" desc="$4" disabled="${5:-}"
  local args=(--name "$name" --every "$every" --description "$desc")
  if $HAS_MODEL; then
    args+=(--message "Run this shell command now using the exec tool: $cmd" --tools "exec")
  else
    args+=(--system-event "exec: $cmd")
  fi
  [[ -n "$disabled" ]] && args+=(--disabled)
  if $DRY_RUN; then
    echo -e "  ${YELLOW}[DRY-RUN]${NC} $OC cron add ${args[*]}"
  else
    $OC cron add "${args[@]}" 2>&1
  fi
}

add_exec_cron_cron() {
  local name="$1" expr="$2" tz="$3" cmd="$4" desc="$5"
  local args=(--name "$name" --cron "$expr" --tz "$tz" --description "$desc")
  if $HAS_MODEL; then
    args+=(--message "Run this shell command now using the exec tool: $cmd" --tools "exec")
  else
    args+=(--system-event "exec: $cmd")
  fi
  if $DRY_RUN; then
    echo -e "  ${YELLOW}[DRY-RUN]${NC} $OC cron add ${args[*]}"
  else
    $OC cron add "${args[@]}" 2>&1
  fi
}

echo -e "\n${BOLD}${CYAN}━━  OpenClaw Cron 등록  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
$DRY_RUN && warn "DRY-RUN 모드 — 실제 등록되지 않습니다"
if $HAS_MODEL; then
  ok "에이전트 모드: ${MODEL_PROVIDER} — 실제 curl 실행"
else
  warn "LLM 키 미설정 → system-event 모니터링 모드 (자동화는 내부 APScheduler 담당)"
fi
echo ""

# ── 1. 30분마다 분석 사이클 트리거 ──────────────────────────────────────────
info "1/4  분석 사이클 트리거 (30분 간격)"
add_exec_cron_every \
  "trading-analysis-cycle" "30m" \
  "curl -s -X POST ${API_URL}/api/v1/scheduler/trigger" \
  "30분마다 뉴스 수집 + 분석 사이클 강제 실행"
ok "등록 완료"

# ── 2. 1시간마다 리스크 상태 체크 ────────────────────────────────────────────
info "2/4  리스크 상태 체크 (1시간 간격)"
add_exec_cron_every \
  "trading-risk-check" "1h" \
  "curl -s ${API_URL}/api/v1/risk/status" \
  "1시간마다 연속손실·거래중단 상태 확인"
ok "등록 완료"

# ── 3. 매일 자정(KST) Fear&Greed 스냅샷 ────────────────────────────────────
info "3/4  일일 시장 스냅샷 (매일 00:00 KST)"
add_exec_cron_cron \
  "trading-daily-snapshot" "0 0 * * *" "Asia/Seoul" \
  "curl -s ${API_URL}/api/v1/fear-greed" \
  "매일 자정(KST) Fear&Greed 지수 스냅샷"
ok "등록 완료"

# ── 4. 웹훅 방식 뉴스 푸시 테스트 (수동용, 비활성화) ───────────────────────
info "4/4  웹훅 뉴스 푸시 테스트 cron (매 시간, 비활성)"
WH_PAYLOAD="{\"token\":\"${WEBHOOK_TOKEN}\",\"symbol\":\"BTCUSDT\",\"news\":[{\"title\":\"Scheduled market check\"}]}"
add_exec_cron_every \
  "trading-webhook-test" "60m" \
  "curl -s -X POST ${API_URL}/api/v1/webhook/news -H 'Content-Type: application/json' -d '${WH_PAYLOAD}'" \
  "매 1시간 웹훅으로 뉴스 분석 트리거 (테스트용)" \
  "disabled"
ok "등록 완료 (비활성화 상태로 생성)"

echo ""
echo -e "${BOLD}${GREEN}━━  등록된 cron 목록  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
$OC cron list 2>&1 || warn "cron list 조회 실패"

echo ""
echo -e "${BOLD}수동 실행 (ID는 위 목록에서 확인):${NC}"
echo -e "  ${CYAN}$OC cron run <id>${NC}           # 즉시 실행"
echo -e "  ${CYAN}$OC cron runs --id <id>${NC}     # 실행 이력"
echo -e "  ${CYAN}$OC cron enable <id>${NC}        # 활성화"
echo -e "  ${CYAN}$OC cron disable <id>${NC}       # 비활성화"
echo -e "  ${CYAN}$OC cron rm <id>${NC}            # 삭제"
echo ""
echo -e "${BOLD}직접 curl 테스트 (gateway 컨테이너에서):${NC}"
echo -e "  ${CYAN}docker exec openclaw-gateway curl -s -X POST ${API_URL}/api/v1/scheduler/trigger${NC}"
echo -e "  ${CYAN}docker exec openclaw-gateway curl -s ${API_URL}/api/v1/risk/status${NC}"
