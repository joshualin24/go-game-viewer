"use strict";

// ── State ────────────────────────────────────────────────────────────────────
const state = {
  games: [],
  currentGame: null,   // parsed game object from /api/game/:filename
  moveIndex: 0,        // 0 = before first move
  boardSize: 19,
  showCoords: true,
  analysis: null,
  katagoAvailable: false,
  autoAnalyze: false,
  loading: false,
};

// ── Canvas helpers ────────────────────────────────────────────────────────────
const canvas = document.getElementById("board-canvas");
const ctx = canvas.getContext("2d");

let CELL = 32;   // px per cell, recalculated on resize
let PAD  = 40;   // padding for coords

function calcLayout() {
  const maxW = canvas.parentElement.clientWidth - 16;
  const maxH = window.innerHeight - 200;
  const sz = state.boardSize;
  const inner = Math.min(maxW - PAD * 2, maxH - PAD * 2);
  CELL = Math.floor(inner / (sz - 1));
  const full = CELL * (sz - 1) + PAD * 2;
  canvas.width = full;
  canvas.height = full;
}

function colX(c) { return PAD + c * CELL; }
function rowY(r) { return PAD + r * CELL; }

// ── Board rendering ───────────────────────────────────────────────────────────
function drawBoard() {
  calcLayout();
  const sz = state.boardSize;
  const W = canvas.width, H = canvas.height;

  // Background
  ctx.fillStyle = "#dcb464";
  ctx.fillRect(0, 0, W, H);

  // Grid lines
  ctx.strokeStyle = "#7a5c1e";
  ctx.lineWidth = 1;
  for (let i = 0; i < sz; i++) {
    ctx.beginPath(); ctx.moveTo(colX(0), rowY(i)); ctx.lineTo(colX(sz - 1), rowY(i)); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(colX(i), rowY(0)); ctx.lineTo(colX(i), rowY(sz - 1)); ctx.stroke();
  }

  // Star points (hoshi)
  const hoshi = getHoshi(sz);
  ctx.fillStyle = "#7a5c1e";
  for (const [r, c] of hoshi) {
    ctx.beginPath();
    ctx.arc(colX(c), rowY(r), CELL * 0.13, 0, Math.PI * 2);
    ctx.fill();
  }

  // Coordinates
  if (state.showCoords) drawCoords(sz);

  // Compute board state up to moveIndex
  const board = buildBoard();

  // Draw stones
  for (let r = 0; r < sz; r++) {
    for (let c = 0; c < sz; c++) {
      if (board[r][c]) drawStone(r, c, board[r][c]);
    }
  }

  // Last move marker
  if (state.moveIndex > 0 && state.currentGame) {
    const moves = state.currentGame.moves;
    for (let i = state.moveIndex - 1; i >= 0; i--) {
      const m = moves[i];
      if (m && "row" in m) {
        drawLastMoveMark(m.row, m.col, m.color);
        break;
      }
    }
  }

  // Analysis heatmap
  if (state.analysis?.top_moves?.length) drawAnalysisHints();
}

function drawCoords(sz) {
  const COLS = "ABCDEFGHJKLMNOPQRST";
  ctx.fillStyle = "#5a3e1b";
  ctx.font = `${Math.max(10, CELL * 0.38)}px monospace`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";

  for (let i = 0; i < sz; i++) {
    // Column letters (top and bottom)
    ctx.fillText(COLS[i], colX(i), PAD * 0.45);
    ctx.fillText(COLS[i], colX(i), rowY(sz - 1) + PAD * 0.55);
    // Row numbers (left and right)
    ctx.fillText(String(sz - i), PAD * 0.45, rowY(i));
    ctx.fillText(String(sz - i), colX(sz - 1) + PAD * 0.55, rowY(i));
  }
}

function drawStone(r, c, color) {
  const x = colX(c), y = rowY(r), radius = CELL * 0.46;
  const isBlack = color === "b";

  // Shadow
  ctx.save();
  ctx.shadowColor = "rgba(0,0,0,0.4)";
  ctx.shadowBlur = CELL * 0.2;
  ctx.shadowOffsetX = CELL * 0.05;
  ctx.shadowOffsetY = CELL * 0.08;

  // Stone gradient
  const grad = ctx.createRadialGradient(
    x - radius * 0.3, y - radius * 0.3, radius * 0.05,
    x, y, radius
  );
  if (isBlack) {
    grad.addColorStop(0, "#555");
    grad.addColorStop(1, "#111");
  } else {
    grad.addColorStop(0, "#ffffff");
    grad.addColorStop(1, "#cccccc");
  }

  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fillStyle = grad;
  ctx.fill();
  ctx.restore();
}

function drawLastMoveMark(r, c, color) {
  const x = colX(c), y = rowY(r);
  ctx.strokeStyle = color === "b" ? "#fff" : "#333";
  ctx.lineWidth = 1.5;
  const s = CELL * 0.18;
  ctx.beginPath();
  ctx.moveTo(x - s, y); ctx.lineTo(x + s, y);
  ctx.moveTo(x, y - s); ctx.lineTo(x, y + s);
  ctx.stroke();
}

function drawAnalysisHints() {
  const top = state.analysis.top_moves;
  if (!top.length) return;
  const bestWr = top[0].win_rate;

  for (let i = 0; i < top.length; i++) {
    const m = top[i];
    const x = colX(m.col), y = rowY(m.row);
    const alpha = i === 0 ? 0.85 : 0.5 - i * 0.08;
    ctx.fillStyle = `rgba(0,200,100,${Math.max(0.2, alpha)})`;
    ctx.beginPath();
    ctx.arc(x, y, CELL * 0.38, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = "#fff";
    ctx.font = `bold ${Math.max(8, CELL * 0.28)}px sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const pct = Math.round(m.win_rate * 100);
    ctx.fillText(`${pct}%`, x, y);
  }
}

// ── Board logic ───────────────────────────────────────────────────────────────
function buildBoard() {
  const sz = state.boardSize;
  const board = Array.from({ length: sz }, () => Array(sz).fill(null));

  if (!state.currentGame) return board;

  // Setup stones (handicap)
  for (const [r, c] of (state.currentGame.setup_stones?.black || [])) board[sz-1-r][c] = "b";
  for (const [r, c] of (state.currentGame.setup_stones?.white || [])) board[sz-1-r][c] = "w";

  const moves = state.currentGame.moves;
  for (let i = 0; i < state.moveIndex; i++) {
    const m = moves[i];
    if (!m || m.move === "pass") continue;
    board[m.row][m.col] = m.color;
    removeCaptures(board, m.row, m.col, m.color, sz);
  }

  return board;
}

function removeCaptures(board, lastR, lastC, color, sz) {
  const opp = color === "b" ? "w" : "b";
  const neighbors = getNeighbors(lastR, lastC, sz);
  for (const [nr, nc] of neighbors) {
    if (board[nr][nc] === opp) {
      const group = getGroup(board, nr, nc, sz);
      if (getLiberties(board, group, sz) === 0) {
        for (const [gr, gc] of group) board[gr][gc] = null;
      }
    }
  }
}

function getGroup(board, r, c, sz) {
  const color = board[r][c];
  const visited = new Set();
  const stack = [[r, c]];
  while (stack.length) {
    const [cr, cc] = stack.pop();
    const key = cr * sz + cc;
    if (visited.has(key)) continue;
    visited.add(key);
    for (const [nr, nc] of getNeighbors(cr, cc, sz)) {
      if (board[nr][nc] === color && !visited.has(nr * sz + nc)) {
        stack.push([nr, nc]);
      }
    }
  }
  return [...visited].map(k => [Math.floor(k / sz), k % sz]);
}

function getLiberties(board, group, sz) {
  const libs = new Set();
  for (const [r, c] of group) {
    for (const [nr, nc] of getNeighbors(r, c, sz)) {
      if (!board[nr][nc]) libs.add(nr * sz + nc);
    }
  }
  return libs.size;
}

function getNeighbors(r, c, sz) {
  const n = [];
  if (r > 0)    n.push([r - 1, c]);
  if (r < sz-1) n.push([r + 1, c]);
  if (c > 0)    n.push([r, c - 1]);
  if (c < sz-1) n.push([r, c + 1]);
  return n;
}

function getHoshi(sz) {
  if (sz === 19) return [[3,3],[3,9],[3,15],[9,3],[9,9],[9,15],[15,3],[15,9],[15,15]];
  if (sz === 13) return [[3,3],[3,9],[9,3],[9,9],[6,6]];
  if (sz === 9)  return [[2,2],[2,6],[6,2],[6,6],[4,4]];
  return [];
}

// ── Navigation ────────────────────────────────────────────────────────────────
function goTo(idx) {
  if (!state.currentGame) return;
  const total = state.currentGame.moves.length;
  state.moveIndex = Math.max(0, Math.min(idx, total));
  drawBoard();
  updateMoveUI();
  if (state.autoAnalyze) analyzeNow();
}

function updateMoveUI() {
  const total = state.currentGame?.moves.length ?? 0;
  document.getElementById("move-counter").textContent = `Move ${state.moveIndex} / ${total}`;
  // Highlight active chip
  document.querySelectorAll(".move-chip").forEach((el, i) => {
    el.classList.toggle("active", parseInt(el.dataset.idx) === state.moveIndex);
  });
  // Scroll active chip into view
  const active = document.querySelector(".move-chip.active");
  if (active) active.scrollIntoView({ inline: "center", block: "nearest" });
}

function buildMoveList() {
  const list = document.getElementById("move-list");
  list.innerHTML = "";

  if (!state.currentGame) return;

  // "Start" chip
  const start = document.createElement("span");
  start.className = "move-chip";
  start.dataset.idx = 0;
  start.textContent = "⬤";
  start.title = "Start";
  start.addEventListener("click", () => goTo(0));
  list.appendChild(start);

  state.currentGame.moves.forEach((m, i) => {
    const chip = document.createElement("span");
    chip.className = `move-chip ${m.color === "b" ? "black" : "white"}`;
    chip.dataset.idx = i + 1;
    const label = m.move === "pass" ? "pass" : coordLabel(m.col, m.row);
    chip.textContent = `${i + 1}:${label}`;
    chip.title = `${i + 1}. ${m.color === "b" ? "Black" : "White"} ${label}`;
    chip.addEventListener("click", () => goTo(i + 1));
    list.appendChild(chip);
  });
}

function coordLabel(col, row) {
  const COLS = "ABCDEFGHJKLMNOPQRST";
  return `${COLS[col]}${state.boardSize - row}`;
}

// ── Canvas click → move navigation ───────────────────────────────────────────
canvas.addEventListener("click", (e) => {
  if (!state.currentGame) return;
  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width / rect.width;
  const scaleY = canvas.height / rect.height;
  const px = (e.clientX - rect.left) * scaleX;
  const py = (e.clientY - rect.top) * scaleY;

  const col = Math.round((px - PAD) / CELL);
  const row = Math.round((py - PAD) / CELL);

  if (col < 0 || row < 0 || col >= state.boardSize || row >= state.boardSize) return;

  // Find the move at this intersection in the remaining moves
  const moves = state.currentGame.moves;
  for (let i = state.moveIndex; i < moves.length; i++) {
    const m = moves[i];
    if ("row" in m && m.row === row && m.col === col) {
      goTo(i + 1);
      return;
    }
  }
  // If not found forward, check backwards
  for (let i = state.moveIndex - 1; i >= 0; i--) {
    const m = moves[i];
    if ("row" in m && m.row === row && m.col === col) {
      goTo(i + 1);
      return;
    }
  }
});

// ── Keyboard navigation ───────────────────────────────────────────────────────
document.addEventListener("keydown", (e) => {
  if (!state.currentGame) return;
  if (e.target.tagName === "INPUT") return;
  const total = state.currentGame.moves.length;
  if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); goTo(state.moveIndex + 1); }
  if (e.key === "ArrowLeft"  || e.key === "ArrowUp")   { e.preventDefault(); goTo(state.moveIndex - 1); }
  if (e.key === "Home") { e.preventDefault(); goTo(0); }
  if (e.key === "End")  { e.preventDefault(); goTo(total); }
  if (e.key === "PageDown") { e.preventDefault(); goTo(state.moveIndex + 10); }
  if (e.key === "PageUp")   { e.preventDefault(); goTo(state.moveIndex - 10); }
});

// ── Game loading ──────────────────────────────────────────────────────────────
async function loadGame(filename) {
  try {
    const res = await fetch(`/api/game/${encodeURIComponent(filename)}`);
    if (!res.ok) throw new Error(await res.text());
    const game = await res.json();

    state.currentGame = game;
    state.boardSize = game.board_size;
    state.moveIndex = 0;
    state.analysis = null;

    const m = game.metadata;
    document.getElementById("info-black").textContent = `⚫ ${m.player_black}${m.black_rank ? ` (${m.black_rank})` : ""}`;
    document.getElementById("info-white").textContent = `⚪ ${m.player_white}${m.white_rank ? ` (${m.white_rank})` : ""}`;
    document.getElementById("info-result").textContent = m.result ? `Result: ${m.result}` : "";

    buildMoveList();
    drawBoard();
    updateMoveUI();
    clearAnalysisUI();

    if (state.autoAnalyze) analyzeNow();
  } catch (err) {
    alert("Failed to load game: " + err.message);
  }
}

// ── Game list ─────────────────────────────────────────────────────────────────
async function refreshGameList() {
  const ul = document.getElementById("game-list");
  ul.innerHTML = "<li style='color:#666'>Loading…</li>";
  try {
    const res = await fetch("/api/games");
    state.games = await res.json();
    renderGameList(state.games);
  } catch {
    ul.innerHTML = "<li style='color:#e94560'>Failed to load games</li>";
  }
}

function renderGameList(games) {
  const ul = document.getElementById("game-list");
  ul.innerHTML = "";

  if (!games.length) {
    ul.innerHTML = "<li style='color:#666;padding:8px'>No games yet. Download some above.</li>";
    return;
  }

  games.forEach(g => {
    const li = document.createElement("li");
    li.innerHTML = `
      <div class="gl-players">⚫ ${esc(g.player_black)} vs ⚪ ${esc(g.player_white)}</div>
      <div class="gl-meta">${esc(g.date)} · ${esc(g.result)} · ${g.board_size}×${g.board_size}</div>
    `;
    li.addEventListener("click", () => {
      document.querySelectorAll("#game-list li").forEach(el => el.classList.remove("active"));
      li.classList.add("active");
      loadGame(g.filename);
    });
    ul.appendChild(li);
  });
}

function esc(s) {
  return String(s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

// ── Download ──────────────────────────────────────────────────────────────────
document.getElementById("btn-download").addEventListener("click", async () => {
  const username = document.getElementById("kgs-username").value.trim();
  const maxGames = parseInt(document.getElementById("kgs-max").value) || 20;
  if (!username) { alert("Enter a KGS username"); return; }

  const status = document.getElementById("download-status");
  status.textContent = `Downloading up to ${maxGames} games for ${username}…`;

  try {
    const res = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, max_games: maxGames }),
    });
    if (!res.ok) throw new Error(await res.text());
    status.textContent = "Download started in background. Refresh the list in a moment.";
    setTimeout(refreshGameList, 5000);
  } catch (err) {
    status.textContent = "Error: " + err.message;
  }
});

document.getElementById("btn-refresh").addEventListener("click", refreshGameList);

// ── Controls ──────────────────────────────────────────────────────────────────
document.getElementById("btn-start").addEventListener("click", () => goTo(0));
document.getElementById("btn-prev").addEventListener("click",  () => goTo(state.moveIndex - 1));
document.getElementById("btn-next").addEventListener("click",  () => goTo(state.moveIndex + 1));
document.getElementById("btn-end").addEventListener("click",   () => goTo(state.currentGame?.moves.length ?? 0));

document.getElementById("chk-coords").addEventListener("change", (e) => {
  state.showCoords = e.target.checked;
  drawBoard();
});

// ── Analysis ──────────────────────────────────────────────────────────────────
async function analyzeNow() {
  if (!state.currentGame) return;

  document.getElementById("analysis-status").textContent = "Analyzing…";
  document.getElementById("btn-analyze").disabled = true;

  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        board_size: state.boardSize,
        moves: state.currentGame.moves,
        move_index: state.moveIndex,
      }),
    });
    const data = await res.json();
    state.analysis = data;
    renderAnalysis(data);
    drawBoard();
    document.getElementById("analysis-status").textContent =
      data.available ? "Analysis complete." : data.error || "KataGo not available.";
  } catch (err) {
    document.getElementById("analysis-status").textContent = "Error: " + err.message;
  } finally {
    document.getElementById("btn-analyze").disabled = false;
  }
}

function renderAnalysis(data) {
  if (!data.available) {
    document.getElementById("wr-black").textContent = "—";
    document.getElementById("wr-white").textContent = "—";
    document.getElementById("score-lead").textContent = "";
    document.querySelector("#top-moves-table tbody").innerHTML = "";
    return;
  }

  const wr = data.win_rate ?? 0.5;
  // win_rate is from black's perspective when black to play, white's when white
  const blackWr = data.color_to_play === "black" ? wr : 1 - wr;
  const whiteWr = 1 - blackWr;

  document.getElementById("winrate-bar-black").style.width = `${blackWr * 100}%`;
  document.getElementById("winrate-bar-white").style.width = `${whiteWr * 100}%`;
  document.getElementById("wr-black").textContent = `${(blackWr * 100).toFixed(1)}%`;
  document.getElementById("wr-white").textContent = `${(whiteWr * 100).toFixed(1)}%`;

  const score = data.score_lead;
  if (score !== null && score !== undefined) {
    const side = score > 0 ? (data.color_to_play === "black" ? "Black" : "White") : (data.color_to_play === "black" ? "White" : "Black");
    document.getElementById("score-lead").textContent = `Score lead: ${side} +${Math.abs(score).toFixed(1)}`;
  }

  const tbody = document.querySelector("#top-moves-table tbody");
  tbody.innerHTML = "";
  (data.top_moves || []).forEach((m, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="${i === 0 ? "tm-best" : ""}">${esc(m.move)}</td>
      <td>${(m.win_rate * 100).toFixed(1)}%</td>
      <td>${m.score > 0 ? "+" : ""}${m.score.toFixed(1)}</td>
      <td>${m.visits}</td>
    `;
    tbody.appendChild(tr);
  });
}

function clearAnalysisUI() {
  state.analysis = null;
  document.getElementById("wr-black").textContent = "—";
  document.getElementById("wr-white").textContent = "—";
  document.getElementById("score-lead").textContent = "";
  document.querySelector("#top-moves-table tbody").innerHTML = "";
  document.getElementById("analysis-status").textContent = "";
}

document.getElementById("btn-analyze").addEventListener("click", analyzeNow);

document.getElementById("chk-auto-analyze").addEventListener("change", (e) => {
  state.autoAnalyze = e.target.checked;
  if (state.autoAnalyze && state.currentGame) analyzeNow();
});

// ── KataGo status check ───────────────────────────────────────────────────────
async function checkKataGo() {
  try {
    const res = await fetch("/api/katago/status");
    const { available } = await res.json();
    state.katagoAvailable = available;
    const badge = document.getElementById("katago-badge");
    badge.textContent = available ? "KataGo ON" : "KataGo OFF";
    badge.className = `badge ${available ? "badge-on" : "badge-off"}`;
  } catch {}
}

// ── Window resize ─────────────────────────────────────────────────────────────
window.addEventListener("resize", () => {
  if (state.currentGame) drawBoard();
});

// ── Init ──────────────────────────────────────────────────────────────────────
(async () => {
  await Promise.all([refreshGameList(), checkKataGo()]);
  // Draw empty board
  state.boardSize = 19;
  drawBoard();
})();
