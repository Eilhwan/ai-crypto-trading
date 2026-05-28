from fastapi import APIRouter
from fastapi.responses import HTMLResponse

dashboard_router = APIRouter()

_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Trading Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg: #0f172a; --surface: #1e293b; --surface2: #273549;
    --border: #334155; --text: #e2e8f0; --muted: #94a3b8;
    --green: #22c55e; --red: #ef4444; --yellow: #eab308;
    --blue: #3b82f6; --purple: #a855f7; --orange: #f97316;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; font-size: 14px; }
  header { background: var(--surface); border-bottom: 1px solid var(--border); padding: 14px 24px; display: flex; align-items: center; justify-content: space-between; }
  header h1 { font-size: 18px; font-weight: 700; letter-spacing: .5px; }
  header h1 span { color: var(--blue); }
  .badge { font-size: 11px; padding: 3px 8px; border-radius: 999px; font-weight: 600; }
  .badge-green { background: #14532d; color: var(--green); }
  .badge-red   { background: #450a0a; color: var(--red); }
  .badge-yellow{ background: #422006; color: var(--yellow); }
  #last-updated { font-size: 12px; color: var(--muted); }
  main { padding: 20px 24px; display: flex; flex-direction: column; gap: 20px; }

  /* Cards row */
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 18px 20px; }
  .card-label { font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); margin-bottom: 10px; }
  .card-value { font-size: 28px; font-weight: 700; line-height: 1; }
  .card-sub   { font-size: 12px; color: var(--muted); margin-top: 6px; }
  .green { color: var(--green); } .red { color: var(--red); }
  .yellow { color: var(--yellow); } .blue { color: var(--blue); }

  /* Risk meter */
  .risk-bar-wrap { margin-top: 10px; height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; }
  .risk-bar { height: 100%; border-radius: 3px; transition: width .4s; }

  /* Sections row */
  .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media(max-width: 900px){ .row2 { grid-template-columns: 1fr; } }

  .panel { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 18px 20px; }
  .panel-title { font-size: 13px; font-weight: 600; margin-bottom: 14px; color: var(--muted); text-transform: uppercase; letter-spacing: .8px; }

  /* Tables */
  .tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
  .tbl th { text-align: left; padding: 6px 8px; color: var(--muted); font-weight: 500; border-bottom: 1px solid var(--border); font-size: 11px; text-transform: uppercase; letter-spacing: .6px; }
  .tbl td { padding: 8px 8px; border-bottom: 1px solid #1e293b; vertical-align: middle; }
  .tbl tr:last-child td { border-bottom: none; }
  .score-pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; }
  .action-badge { font-size: 11px; padding: 2px 6px; border-radius: 4px; font-weight: 600; }

  /* Chart canvas */
  #scoreChart { max-height: 220px; }

  /* Halt banner */
  #halt-banner { display: none; background: #450a0a; border: 1px solid var(--red); border-radius: 8px; padding: 12px 18px; color: var(--red); font-weight: 600; font-size: 14px; }
  #halt-banner button { margin-left: 16px; background: var(--red); color: #fff; border: none; border-radius: 6px; padding: 4px 12px; cursor: pointer; font-size: 12px; }

  /* FG gauge */
  .fg-gauge { position: relative; height: 10px; background: linear-gradient(to right, var(--red) 0%, var(--yellow) 50%, var(--green) 100%); border-radius: 5px; margin-top: 10px; }
  .fg-needle { position: absolute; top: -4px; width: 4px; height: 18px; background: #fff; border-radius: 2px; transform: translateX(-50%); transition: left .4s; }

  /* Spinner */
  .spin { animation: spin 1s linear infinite; display: inline-block; }
  @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
  .empty { color: var(--muted); font-size: 13px; text-align: center; padding: 20px 0; }
</style>
</head>
<body>

<header>
  <h1>AI <span>Crypto</span> Trading Dashboard</h1>
  <div style="display:flex;align-items:center;gap:12px;">
    <span id="health-badge" class="badge badge-yellow">…</span>
    <span id="last-updated">--</span>
  </div>
</header>

<main>
  <!-- Halt Banner -->
  <div id="halt-banner">
    ⛔ 거래 중단됨 — <span id="halt-reason"></span>
    <button onclick="resetRisk()">리셋</button>
  </div>

  <!-- Status Cards -->
  <div class="cards">
    <div class="card">
      <div class="card-label">Fear &amp; Greed</div>
      <div class="card-value" id="fg-value">--</div>
      <div class="card-sub" id="fg-class">--</div>
      <div class="fg-gauge"><div class="fg-needle" id="fg-needle" style="left:50%"></div></div>
    </div>
    <div class="card">
      <div class="card-label">스케줄러</div>
      <div class="card-value blue" id="sched-status">--</div>
      <div class="card-sub" id="sched-next">--</div>
    </div>
    <div class="card">
      <div class="card-label">연속 손실</div>
      <div class="card-value" id="consec-loss">--</div>
      <div class="card-sub" id="consec-sub">--</div>
      <div class="risk-bar-wrap"><div class="risk-bar" id="consec-bar" style="width:0%;background:var(--green)"></div></div>
    </div>
    <div class="card">
      <div class="card-label">일일 손실</div>
      <div class="card-value" id="daily-loss">--</div>
      <div class="card-sub" id="daily-sub">--</div>
    </div>
    <div class="card">
      <div class="card-label">총 분석</div>
      <div class="card-value blue" id="total-analysis">--</div>
      <div class="card-sub">누적 분석 횟수</div>
    </div>
    <div class="card">
      <div class="card-label">총 거래</div>
      <div class="card-value" id="total-trades">--</div>
      <div class="card-sub" id="win-rate-sub">--</div>
    </div>
  </div>

  <!-- Score Chart + Recent Trades -->
  <div class="row2">
    <div class="panel">
      <div class="panel-title">최근 분석 점수</div>
      <canvas id="scoreChart"></canvas>
    </div>
    <div class="panel">
      <div class="panel-title">최근 거래</div>
      <table class="tbl">
        <thead><tr><th>심볼</th><th>방향</th><th>수량</th><th>결과</th><th>시각</th></tr></thead>
        <tbody id="trades-body"><tr><td colspan="5" class="empty">데이터 없음</td></tr></tbody>
      </table>
    </div>
  </div>

  <!-- Analysis Logs -->
  <div class="panel">
    <div class="panel-title">최근 분석 로그</div>
    <table class="tbl">
      <thead><tr><th>심볼</th><th>점수</th><th>행동</th><th>판단 근거</th><th>시각</th></tr></thead>
      <tbody id="analysis-body"><tr><td colspan="5" class="empty">데이터 없음</td></tr></tbody>
    </table>
  </div>

  <!-- Backtest History -->
  <div class="panel">
    <div class="panel-title">백테스트 이력</div>
    <table class="tbl">
      <thead><tr><th>심볼</th><th>기간</th><th>수익률</th><th>MDD</th><th>승률</th><th>샤프</th><th>거래수</th><th>시각</th></tr></thead>
      <tbody id="backtest-body"><tr><td colspan="8" class="empty">데이터 없음</td></tr></tbody>
    </table>
  </div>
</main>

<script>
const API = '/api/v1';
let scoreChart;

// ── helpers ──────────────────────────────────────────────────────────────────
const fmtTime = iso => {
  if (!iso) return '--';
  const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
  return d.toLocaleTimeString('ko-KR', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
};

const scoreColor = s => {
  const a = Math.abs(s);
  if (a >= 20) return s > 0 ? '#22c55e' : '#ef4444';
  if (a >= 10) return '#eab308';
  return '#94a3b8';
};

const actionBadge = a => {
  const map = {
    auto_trade: ['#14532d','#22c55e','자동거래'],
    notify:     ['#422006','#eab308','승인요청'],
    ignore:     ['#1e293b','#94a3b8','무시'],
  };
  const [bg, fg, label] = map[a] || ['#1e293b','#94a3b8', a];
  return `<span class="action-badge" style="background:${bg};color:${fg}">${label}</span>`;
};

// ── fetch & render ────────────────────────────────────────────────────────────
async function fetchAll() {
  try {
    const [health, fg, sched, risk, analysis, trades, btLogs] = await Promise.all([
      fetch(`${API}/health`).then(r=>r.json()).catch(()=>({})),
      fetch(`${API}/fear-greed`).then(r=>r.json()).catch(()=>({})),
      fetch(`${API}/scheduler/status`).then(r=>r.json()).catch(()=>({})),
      fetch(`${API}/risk/status`).then(r=>r.json()).catch(()=>({})),
      fetch(`${API}/logs/analysis?limit=20`).then(r=>r.json()).catch(()=>[]),
      fetch(`${API}/logs/trades?limit=10`).then(r=>r.json()).catch(()=>[]),
      fetch(`${API}/backtest/results?limit=5`).then(r=>r.json()).catch(()=>[]),
    ]);

    renderHealth(health);
    renderFearGreed(fg);
    renderScheduler(sched);
    renderRisk(risk);
    renderAnalysis(analysis);
    renderTrades(trades);
    renderBacktest(btLogs);

    document.getElementById('last-updated').textContent = '업데이트: ' + new Date().toLocaleTimeString('ko-KR');
  } catch(e) { console.error(e); }
}

function renderHealth(h) {
  const el = document.getElementById('health-badge');
  const halted = h.trading_halted;
  el.textContent = halted ? '거래중단' : (h.status === 'ok' ? '정상' : '오류');
  el.className = 'badge ' + (halted ? 'badge-red' : h.status === 'ok' ? 'badge-green' : 'badge-yellow');
}

function renderFearGreed(fg) {
  const v = fg.value ?? 50;
  document.getElementById('fg-value').textContent = Math.round(v);
  document.getElementById('fg-class').textContent = fg.classification ?? '--';
  document.getElementById('fg-value').className = 'card-value ' + (v < 25 ? 'green' : v > 75 ? 'red' : 'yellow');
  document.getElementById('fg-needle').style.left = v + '%';
}

function renderScheduler(s) {
  document.getElementById('sched-status').textContent = s.running ? '실행 중' : '중지';
  const next = s.next_run ? fmtTime(s.next_run) : '--';
  document.getElementById('sched-next').textContent = `다음 실행: ${next} | ${(s.watch_symbols||[]).join(', ')}`;
}

function renderRisk(r) {
  const cl = r.consecutive_losses ?? 0;
  const max = r.max_consecutive_losses ?? 5;
  const daily = r.daily_loss_usdt ?? 0;
  const halted = r.trading_halted;

  document.getElementById('consec-loss').textContent = cl;
  document.getElementById('consec-loss').className = 'card-value ' + (halted ? 'red' : cl >= max * 0.6 ? 'yellow' : 'green');
  document.getElementById('consec-sub').textContent = `한도: ${max}회`;

  const pct = Math.min(cl / max * 100, 100);
  const bar = document.getElementById('consec-bar');
  bar.style.width = pct + '%';
  bar.style.background = pct >= 80 ? 'var(--red)' : pct >= 50 ? 'var(--yellow)' : 'var(--green)';

  document.getElementById('daily-loss').textContent = `-${daily.toFixed(2)} USDT`;
  document.getElementById('daily-loss').className = 'card-value ' + (daily > 0 ? 'red' : 'green');
  document.getElementById('daily-sub').textContent = `한도: -${r.max_daily_loss_pct ?? 3}%`;

  const banner = document.getElementById('halt-banner');
  if (halted) {
    banner.style.display = 'block';
    document.getElementById('halt-reason').textContent = r.halted_reason;
  } else {
    banner.style.display = 'none';
  }
}

function renderAnalysis(logs) {
  document.getElementById('total-analysis').textContent = logs.length >= 20 ? '20+' : logs.length;

  const tbody = document.getElementById('analysis-body');
  if (!logs.length) { tbody.innerHTML = '<tr><td colspan="5" class="empty">데이터 없음</td></tr>'; return; }

  tbody.innerHTML = logs.map(l => {
    const col = scoreColor(l.score);
    const pill = `<span class="score-pill" style="background:${col}22;color:${col}">${l.score > 0 ? '+' : ''}${l.score?.toFixed(1)}</span>`;
    const reason = (l.reasoning || '').split('|').slice(1).join(' |').trim().substring(0, 80);
    return `<tr>
      <td><b>${l.symbol}</b></td>
      <td>${pill}</td>
      <td>${actionBadge(l.action)}</td>
      <td style="color:var(--muted);max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${reason || '--'}</td>
      <td style="color:var(--muted)">${fmtTime(l.created_at)}</td>
    </tr>`;
  }).join('');

  // Score chart
  const labels = [...logs].reverse().map((l, i) => i + 1);
  const scores = [...logs].reverse().map(l => l.score);
  const bgColors = scores.map(s => {
    const a = Math.abs(s);
    if (a >= 20) return s > 0 ? '#22c55e66' : '#ef444466';
    if (a >= 10) return '#eab30866';
    return '#94a3b844';
  });
  const borderColors = scores.map(s => {
    const a = Math.abs(s);
    if (a >= 20) return s > 0 ? '#22c55e' : '#ef4444';
    if (a >= 10) return '#eab308';
    return '#94a3b8';
  });

  if (scoreChart) scoreChart.destroy();
  const ctx = document.getElementById('scoreChart').getContext('2d');
  scoreChart = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets: [{
      label: '점수',
      data: scores,
      backgroundColor: bgColors,
      borderColor: borderColors,
      borderWidth: 1.5,
      borderRadius: 4,
    }]},
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => ` Score: ${c.raw > 0 ? '+' : ''}${c.raw}` } }
      },
      scales: {
        x: { grid: { color: '#334155' }, ticks: { color: '#94a3b8' } },
        y: {
          grid: { color: '#334155' }, ticks: { color: '#94a3b8' },
          title: { display: true, text: '점수', color: '#94a3b8', font: { size: 11 } }
        }
      }
    }
  });
}

function renderTrades(trades) {
  document.getElementById('total-trades').textContent = trades.length;
  const wins = trades.filter(t => t.success).length;
  document.getElementById('win-rate-sub').textContent = trades.length ? `성공 ${wins}/${trades.length}` : '거래 없음';

  const tbody = document.getElementById('trades-body');
  if (!trades.length) { tbody.innerHTML = '<tr><td colspan="5" class="empty">데이터 없음</td></tr>'; return; }

  tbody.innerHTML = trades.map(t => {
    const sideColor = t.side === 'Buy' ? 'var(--green)' : 'var(--red)';
    const okBadge = t.success
      ? '<span class="badge badge-green">성공</span>'
      : '<span class="badge badge-red">실패</span>';
    return `<tr>
      <td><b>${t.symbol}</b></td>
      <td style="color:${sideColor};font-weight:600">${t.side}</td>
      <td>${t.qty}</td>
      <td>${okBadge}</td>
      <td style="color:var(--muted)">${fmtTime(t.created_at)}</td>
    </tr>`;
  }).join('');
}

function renderBacktest(logs) {
  const tbody = document.getElementById('backtest-body');
  if (!logs.length) { tbody.innerHTML = '<tr><td colspan="8" class="empty">데이터 없음</td></tr>'; return; }

  tbody.innerHTML = logs.map(b => {
    const retColor = b.total_return_pct >= 0 ? 'var(--green)' : 'var(--red)';
    const sign = b.total_return_pct >= 0 ? '+' : '';
    return `<tr>
      <td><b>${b.symbol}</b></td>
      <td>${b.days}d / ${b.interval}m</td>
      <td style="color:${retColor};font-weight:600">${sign}${b.total_return_pct?.toFixed(2)}%</td>
      <td style="color:var(--red)">${b.max_drawdown_pct?.toFixed(2)}%</td>
      <td>${b.win_rate?.toFixed(1)}%</td>
      <td>${b.sharpe_ratio?.toFixed(2) ?? '--'}</td>
      <td>${b.total_trades}</td>
      <td style="color:var(--muted)">${fmtTime(b.created_at)}</td>
    </tr>`;
  }).join('');
}

async function resetRisk() {
  await fetch(`${API}/risk/reset`, { method: 'POST' });
  fetchAll();
}

// ── init ─────────────────────────────────────────────────────────────────────
fetchAll();
setInterval(fetchAll, 10000);
</script>
</body>
</html>
"""


@dashboard_router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    return _HTML
