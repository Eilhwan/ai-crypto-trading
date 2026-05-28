#!/usr/bin/env bash
# AI Crypto Trading System — 통합 시작 스크립트
set -euo pipefail

# ── 색상 ──────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── 출력 헬퍼 ─────────────────────────────────────────────────────────────────
info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }
section() { echo -e "\n${BOLD}${CYAN}━━  $*  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

# ── 사용법 ────────────────────────────────────────────────────────────────────
usage() {
  echo -e "
${BOLD}사용법:${NC}
  ./start.sh [COMMAND] [OPTIONS]

${BOLD}Commands:${NC}
  up        서비스 시작 (기본값)
  down      서비스 중지
  restart   서비스 재시작
  status    서비스 상태 확인
  logs      로그 스트리밍
  pull      Ollama 모델 pull (full 모드만)

${BOLD}Options:${NC}
  --mock    Mock 모드로 시작 (기본값 — API 키·ML 모델 불필요)
  --full    전체 모드 (FinBERT + Ollama + Bybit 실연동)

${BOLD}예시:${NC}
  ./start.sh                   # mock 모드로 시작
  ./start.sh up --full         # full 모드로 시작
  ./start.sh down              # 전체 중지
  ./start.sh logs              # 로그 보기
  ./start.sh status            # 상태 확인
"
}

# ── 인자 파싱 ─────────────────────────────────────────────────────────────────
COMMAND="up"
MODE="mock"

for arg in "$@"; do
  case "$arg" in
    up|down|restart|status|logs|pull) COMMAND="$arg" ;;
    --mock) MODE="mock" ;;
    --full) MODE="full" ;;
    -h|--help) usage; exit 0 ;;
    *) warn "알 수 없는 옵션: $arg"; usage; exit 1 ;;
  esac
done

COMPOSE_FILE="docker-compose.mock.yml"
CONTAINER_NAME="trading-api-mock"
[[ "$MODE" == "full" ]] && COMPOSE_FILE="docker-compose.yml" && CONTAINER_NAME="trading-api"

# ── 사전 점검 ─────────────────────────────────────────────────────────────────
check_prerequisites() {
  section "사전 점검"

  if ! command -v docker &>/dev/null; then
    error "Docker가 설치되어 있지 않습니다."
    exit 1
  fi
  ok "Docker: $(docker --version | awk '{print $3}' | tr -d ',')"

  if ! docker info &>/dev/null; then
    error "Docker 데몬이 실행 중이지 않습니다. Docker Desktop을 시작해주세요."
    exit 1
  fi
  ok "Docker 데몬 실행 중"

  if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    warn ".env 파일이 없습니다. .env.example을 복사합니다."
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    warn ".env 파일을 열어 API 키를 설정하세요: $SCRIPT_DIR/.env"
  else
    ok ".env 파일 확인"
  fi

  mkdir -p "$SCRIPT_DIR/data"
  ok "data/ 디렉토리 준비"
}

# ── OpenClaw 상태 확인 ────────────────────────────────────────────────────────
check_openclaw() {
  section "OpenClaw 상태"
  if docker ps --format '{{.Names}}' | grep -q "openclaw.*gateway"; then
    local port
    port=$(docker ps --format '{{.Names}} {{.Ports}}' \
      | grep "openclaw.*gateway" \
      | grep -oE '0\.0\.0\.0:[0-9]+' | head -1 | cut -d: -f2)
    ok "OpenClaw 실행 중 (포트: ${port:-18789})"
    ok "trading-api → OpenClaw: http://host.docker.internal:${port:-18789}"
  else
    warn "OpenClaw가 실행 중이지 않습니다."
    warn "알림 기능을 사용하려면 OpenClaw를 별도로 시작해주세요:"
    echo -e "  ${CYAN}cd ~/Documents/openclaw/openclaw-in-docker && docker compose up -d${NC}"
  fi
}

# ── Ollama 상태 확인 / 모델 pull ──────────────────────────────────────────────
check_ollama() {
  if [[ "$MODE" != "full" ]]; then return; fi

  section "Ollama"
  local model
  model=$(grep "^OLLAMA_MODEL=" "$SCRIPT_DIR/.env" 2>/dev/null | cut -d= -f2 || echo "llama3.2")

  if docker ps --format '{{.Names}}' | grep -q "^ollama$"; then
    ok "Ollama 실행 중"
    if docker exec ollama ollama list 2>/dev/null | grep -q "$model"; then
      ok "모델 '$model' 준비됨"
    else
      info "모델 '$model' pull 중... (시간이 걸릴 수 있습니다)"
      docker exec ollama ollama pull "$model"
      ok "모델 '$model' 다운로드 완료"
    fi
  else
    info "Ollama는 docker compose up 후 시작됩니다."
  fi
}

# ── 헬스체크 대기 ─────────────────────────────────────────────────────────────
wait_healthy() {
  local name="$1"
  local max_wait=60
  local elapsed=0

  printf "  %s 준비 대기 중 " "$name"
  while true; do
    local health
    health=$(docker inspect --format='{{.State.Health.Status}}' "$name" 2>/dev/null || echo "none")

    if [[ "$health" == "healthy" ]]; then
      echo -e " ${GREEN}✓${NC}"
      return 0
    elif [[ "$health" == "unhealthy" ]]; then
      echo -e " ${RED}✗${NC}"
      error "$name 헬스체크 실패. 로그 확인: docker logs $name"
      return 1
    fi

    if [[ $elapsed -ge $max_wait ]]; then
      echo -e " ${YELLOW}?${NC}"
      warn "$name 헬스체크 타임아웃 (${max_wait}s). 계속 진행합니다."
      return 0
    fi

    printf "."
    sleep 2
    ((elapsed += 2))
  done
}

# ── 서비스 시작 ───────────────────────────────────────────────────────────────
cmd_up() {
  check_prerequisites
  check_openclaw

  section "서비스 시작 (${MODE} 모드)"
  info "Compose 파일: $COMPOSE_FILE"

  cd "$SCRIPT_DIR"
  docker compose -f "$COMPOSE_FILE" up -d --build

  section "헬스체크"
  [[ "$MODE" == "full" ]] && wait_healthy "ollama"
  wait_healthy "$CONTAINER_NAME"

  check_ollama
  print_status
}

# ── 서비스 중지 ───────────────────────────────────────────────────────────────
cmd_down() {
  section "서비스 중지"
  cd "$SCRIPT_DIR"

  # 실행 중인 compose 파일 자동 감지
  if docker ps --format '{{.Names}}' | grep -q "^trading-api-mock$"; then
    info "Mock 모드 서비스 중지 중..."
    docker compose -f docker-compose.mock.yml down
  fi
  if docker ps --format '{{.Names}}' | grep -q "^trading-api$"; then
    info "Full 모드 서비스 중지 중..."
    docker compose -f docker-compose.yml down
  fi
  ok "서비스 중지 완료"
}

# ── 재시작 ────────────────────────────────────────────────────────────────────
cmd_restart() {
  cmd_down
  cmd_up
}

# ── 상태 출력 ─────────────────────────────────────────────────────────────────
print_status() {
  section "서비스 현황"

  echo -e "${BOLD}  컨테이너${NC}"
  docker ps --format "  {{.Names}}\t{{.Status}}\t{{.Ports}}" \
    | grep -E "trading-api|ollama|openclaw" \
    | while IFS=$'\t' read -r name status ports; do
        if echo "$status" | grep -q "Up"; then
          echo -e "  ${GREEN}●${NC} ${BOLD}${name}${NC}  ${status}  ${CYAN}${ports}${NC}"
        else
          echo -e "  ${RED}●${NC} ${BOLD}${name}${NC}  ${status}"
        fi
      done

  echo ""
  echo -e "${BOLD}  엔드포인트${NC}"
  echo -e "  ${CYAN}http://localhost:8000${NC}          Trading API"
  echo -e "  ${CYAN}http://localhost:8000/docs${NC}     Swagger UI"
  echo -e "  ${CYAN}http://localhost:8000/api/v1/health${NC}"
  if [[ "$MODE" == "full" ]]; then
    echo -e "  ${CYAN}http://localhost:11434${NC}         Ollama"
  fi
  echo ""

  echo -e "${BOLD}  빠른 테스트${NC}"
  echo -e "  ${YELLOW}curl -s http://localhost:8000/api/v1/health | python3 -m json.tool${NC}"
  echo ""
  echo -e "  ${YELLOW}curl -s -X POST http://localhost:8000/api/v1/analyze \\
    -H 'Content-Type: application/json' \\
    -d '{\"symbol\":\"BTCUSDT\",\"news\":[{\"title\":\"Bitcoin ETF approved\"}]}'${NC}"
}

cmd_status() {
  check_openclaw
  print_status
}

# ── 로그 ──────────────────────────────────────────────────────────────────────
cmd_logs() {
  if docker ps --format '{{.Names}}' | grep -q "^trading-api-mock$"; then
    docker logs -f trading-api-mock
  elif docker ps --format '{{.Names}}' | grep -q "^trading-api$"; then
    docker logs -f trading-api
  else
    error "실행 중인 trading-api 컨테이너가 없습니다."
    exit 1
  fi
}

# ── Ollama 모델 수동 pull ─────────────────────────────────────────────────────
cmd_pull() {
  local model
  model=$(grep "^OLLAMA_MODEL=" "$SCRIPT_DIR/.env" 2>/dev/null | cut -d= -f2 || echo "llama3.2")
  section "Ollama 모델 pull: $model"
  if ! docker ps --format '{{.Names}}' | grep -q "^ollama$"; then
    error "Ollama 컨테이너가 실행 중이지 않습니다. './start.sh up --full' 먼저 실행하세요."
    exit 1
  fi
  docker exec ollama ollama pull "$model"
  ok "'$model' 모델 준비 완료"
}

# ── 배너 ──────────────────────────────────────────────────────────────────────
echo -e "
${BOLD}${CYAN}
  ╔═══════════════════════════════════════╗
  ║   AI Crypto Trading System  v0.1     ║
  ╚═══════════════════════════════════════╝
${NC}  모드: ${BOLD}${MODE}${NC}  |  커맨드: ${BOLD}${COMMAND}${NC}
"

# ── 커맨드 디스패치 ───────────────────────────────────────────────────────────
case "$COMMAND" in
  up)      cmd_up ;;
  down)    cmd_down ;;
  restart) cmd_restart ;;
  status)  cmd_status ;;
  logs)    cmd_logs ;;
  pull)    cmd_pull ;;
esac
