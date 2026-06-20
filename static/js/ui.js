// ── UI Module ──
// Pure DOM rendering functions, view management, toasts

// View management
export function setView(name) {
  const history = document.getElementById('history-panel');
  const config = document.getElementById('config-panel');
  const grid = document.getElementById('debate-grid');
  const ctrl = document.getElementById('control-bar');
  const verdict = document.getElementById('verdict-section');
  const backBtn = document.getElementById('back-list-btn');
  const newBtn = document.getElementById('new-debate-btn');

  switch (name) {
    case 'config':
    case 'history':
      history.style.display = '';
      config.classList.remove('hidden');
      grid.style.display = 'none';
      ctrl.style.display = 'none';
      verdict.style.display = 'none';
      backBtn.style.display = 'none';
      newBtn.style.display = 'none';
      break;
    case 'debate':
      history.style.display = 'none';
      config.classList.add('hidden');
      grid.style.display = 'grid';
      ctrl.style.display = 'flex';
      verdict.style.display = 'none';
      backBtn.style.display = 'inline-block';
      newBtn.style.display = 'inline-block';
      break;
  }
}

// ── Debate Grid ──

export const DEBATER_KEYS = ['pro_1', 'pro_2', 'pro_3', 'con_1', 'con_2', 'con_3'];

export function clearAllCells() {
  DEBATER_KEYS.forEach(key => {
    const cell = document.getElementById('cell-' + key);
    if (cell) cell.classList.remove('active');
    const status = document.getElementById('status-' + key);
    if (status) { status.textContent = '等待'; status.className = 'status-badge'; }
    const thinking = document.getElementById('thinking-' + key);
    if (thinking) thinking.textContent = '';
    const speech = document.getElementById('speech-' + key);
    if (speech) speech.textContent = '';
    const details = document.getElementById('details-' + key);
    if (details) details.open = false;
  });
  // Also clear judge cells if present
  const judgeCell = document.getElementById('cell-judge');
  if (judgeCell) judgeCell.classList.remove('active');
}

export function highlightSpeaker(debater) {
  DEBATER_KEYS.forEach(key => {
    const cell = document.getElementById('cell-' + key);
    if (cell) cell.classList.remove('active');
  });
  const cell = document.getElementById('cell-' + debater);
  if (cell) cell.classList.add('active');
}

export function setBadgeStatus(debater, status) {
  const badge = document.getElementById('status-' + debater);
  if (!badge) return;
  badge.classList.remove('thinking', 'speaking', 'done', 'finishing');
  if (status === 'thinking') {
    badge.textContent = '思考中';
    badge.classList.add('thinking');
  } else if (status === 'speaking') {
    badge.textContent = '发言中';
    badge.classList.add('speaking');
  } else if (status === 'finishing') {
    // Intermediate: speech done, but typewriter still rendering
    badge.textContent = '输出中';
    badge.classList.add('finishing');
  } else if (status === 'done') {
    badge.textContent = '已完成';
    badge.classList.add('done');
  } else {
    badge.textContent = '等待';
  }
}

export function updateAllStatusBadges(debaterStatus) {
  DEBATER_KEYS.forEach(key => {
    // Don't override "finishing" or "speaking" state with backend data —
    // let render queue / typewriter finish first.
    const badge = document.getElementById('status-' + key);
    if (badge && (badge.classList.contains('finishing') || badge.classList.contains('speaking') || badge.classList.contains('thinking'))) {
      return;
    }
    const status = debaterStatus[key] || 'waiting';
    setBadgeStatus(key, status);
  });
}

// ── Control Info ──

const PHASE_NAMES = {
  'begin': '准备中',
  'pro_opening': '正方立论',
  'con_opening': '反方立论',
  'pro_rebuttal': '正方驳论',
  'con_rebuttal': '反方驳论',
  'pro_argument': '正方论证',
  'con_argument': '反方论证',
  'free_debate': '自由辩论',
  'pro_closing': '正方总结',
  'con_closing': '反方总结',
  'verdict': '裁判裁决',
};

export function getPhaseName(phase) {
  return PHASE_NAMES[phase] || phase;
}

export function updateControlInfo(round, totalRounds, phase) {
  const roundInfo = document.getElementById('round-info');
  if (round && totalRounds) {
    roundInfo.textContent = '第 ' + round + '/' + totalRounds + ' 轮';
  } else if (totalRounds) {
    roundInfo.textContent = '共 ' + totalRounds + ' 轮';
  }
  if (phase) {
    document.getElementById('phase-info').textContent = PHASE_NAMES[phase] || phase;
  }
}

// ── Verdict ──

export function showVerdict(verdict, winner) {
  document.getElementById('verdict-section').style.display = 'block';
  const winnerMap = { pro: '正方获胜！', con: '反方获胜！', draw: '平局！' };
  const winnerEl = document.getElementById('verdict-winner');
  winnerEl.textContent = winnerMap[winner] || '结果未知';
  const winnerClassMap = { pro: 'pro-wins', con: 'con-wins', draw: 'draw' };
  winnerEl.className = winnerClassMap[winner] || '';

  const proScores = verdict.pro_scores || {};
  const conScores = verdict.con_scores || {};

  // Map judge JSON keys to HTML columns
  const dimensionMapping = [
    { key: 'argument',   label: '论证严谨度' },
    { key: 'rebuttal',   label: '反驳有效性' },
    { key: 'expression', label: '表达清晰度' },
    { key: 'teamwork',   label: '数据与事实支撑' },
  ];

  dimensionMapping.forEach(({ key, label }) => {
    const proCell = document.getElementById('score-' + key + '-pro');
    const conCell = document.getElementById('score-' + key + '-con');
    if (proCell) proCell.textContent = proScores[label] || '-';
    if (conCell) conCell.textContent = conScores[label] || '-';
  });

  const proTotal = document.getElementById('score-total-pro');
  const conTotal = document.getElementById('score-total-con');
  if (proTotal) proTotal.textContent = proScores.total || '-';
  if (conTotal) conTotal.textContent = conScores.total || '-';

  document.getElementById('verdict-summary').textContent = verdict.summary || '';
}

// ── Toasts ──

let toastTimer = null;

export function showToast(message, type = 'error') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = 'toast ' + type;
  toast.textContent = message;
  container.appendChild(toast);

  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.classList.add('exiting');
    setTimeout(() => toast.remove(), 300);
  }, 5000);
}

// ── Modal ──

export function showModal(id) {
  document.getElementById(id).style.display = 'flex';
}

export function hideModal(id) {
  document.getElementById(id).style.display = 'none';
}

// ── Helpers ──

// ── Fullscreen Toggle ──

export function toggleDebaterFullscreen(cell) {
  const isFullscreen = cell.classList.contains('fullscreen');
  if (isFullscreen) {
    cell.classList.remove('fullscreen');
  } else {
    cell.classList.add('fullscreen');
  }
  _updateFullscreenButton(cell);
}

function _updateFullscreenButton(cell) {
  const btn = cell.querySelector('.fullscreen-btn');
  if (!btn) return;
  const isFullscreen = cell.classList.contains('fullscreen');
  btn.title = isFullscreen ? '还原' : '全屏查看';
  btn.textContent = isFullscreen ? '↙' : '↗';
}

export function injectFullscreenButtons() {
  document.querySelectorAll('.debater-cell').forEach(cell => {
    if (cell.querySelector('.fullscreen-btn')) return;
    const btn = document.createElement('button');
    btn.className = 'fullscreen-btn';
    btn.title = '全屏查看';
    btn.textContent = '↗';
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleDebaterFullscreen(cell);
    });
    const header = cell.querySelector('.cell-header');
    if (header) header.appendChild(btn);
  });
}

let _escapeHandlerInstalled = false;

export function initFullscreenEscapeHandler() {
  if (_escapeHandlerInstalled) return;
  _escapeHandlerInstalled = true;
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    const fsCell = document.querySelector('.debater-cell.fullscreen');
    if (fsCell) toggleDebaterFullscreen(fsCell);
  });
}

export function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

export function formatTime(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts + 'Z');
    const now = new Date();
    const diffMs = now - d;
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return '刚刚';
    if (diffMins < 60) return diffMins + '分钟前';
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return diffHours + '小时前';
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return diffDays + '天前';
    return d.toLocaleDateString('zh-CN');
  } catch (e) {
    return ts;
  }
}
