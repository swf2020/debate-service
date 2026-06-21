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

  const show = (el, display) => { if (el) el.style.display = display; };
  const addHidden = (el) => { if (el) el.classList.add('hidden'); };
  const removeHidden = (el) => { if (el) el.classList.remove('hidden'); };

  switch (name) {
    case 'config':
    case 'history':
      show(history, '');
      removeHidden(config);
      show(grid, 'none');
      show(ctrl, 'none');
      show(verdict, 'none');
      show(backBtn, 'none');
      show(newBtn, 'none');
      break;
    case 'debate':
      show(history, 'none');
      addHidden(config);
      show(grid, 'flex');
      show(ctrl, 'flex');
      show(verdict, 'none');
      show(backBtn, 'inline-block');
      show(newBtn, 'inline-block');
      break;
  }
}

// ── Debate Grid ──

export const DEBATER_KEYS = ['pro_1', 'pro_2', 'pro_3', 'pro_4', 'con_1', 'con_2', 'con_3', 'con_4'];

// All 22 role_ids in the 4-module layout
export const ALL_ROLE_IDS = [
  'pro_1:pro_opening', 'con_1:con_opening',
  'con_2:con_argument', 'pro_2:pro_argument',
  'pro_3:pro_cross_examine', 'con_2:pro_cross_examine_response', 'con_3:pro_cross_examine_response',
  'con_3:con_cross_examine', 'pro_2:con_cross_examine_response', 'pro_3:con_cross_examine_response',
  'con_3:con_cross_summary', 'pro_3:pro_cross_summary',
  'pro_1:free_debate', 'con_1:free_debate', 'pro_2:free_debate', 'con_2:free_debate',
  'pro_3:free_debate', 'con_3:free_debate', 'pro_4:free_debate', 'con_4:free_debate',
  'con_4:con_closing', 'pro_4:pro_closing',
];

let _activeRoleBox = null;

export function highlightRoleBox(roleId) {
  if (_activeRoleBox && _activeRoleBox !== roleId) {
    const prev = document.getElementById('rolebox-' + _activeRoleBox);
    if (prev) prev.classList.remove('active');
  }
  _activeRoleBox = roleId;
  const box = document.getElementById('rolebox-' + roleId);
  if (box) box.classList.add('active');
}

export function setRoleBoxStatus(roleId, status) {
  const badge = document.getElementById('status-' + roleId);
  if (!badge) return;
  badge.classList.remove('thinking', 'speaking', 'done');
  if (status === 'thinking') {
    badge.textContent = '思考中';
    badge.classList.add('thinking');
  } else if (status === 'speaking') {
    badge.textContent = '发言中';
    badge.classList.add('speaking');
  } else if (status === 'done') {
    badge.textContent = '已完成';
    badge.classList.add('done');
  } else {
    badge.textContent = '等待';
  }
}

export function clearRoleBox(roleId) {
  const speech = document.getElementById('speech-' + roleId);
  if (speech) speech.textContent = '';
  const thinking = document.getElementById('thinking-' + roleId);
  if (thinking) thinking.textContent = '';
  const details = document.getElementById('details-' + roleId);
  if (details) {
    details.open = false;
    const summary = details.querySelector('summary');
    if (summary) summary.textContent = '思考过程';
  }
}

export function clearAllRoleBoxes() {
  ALL_ROLE_IDS.forEach(roleId => {
    const box = document.getElementById('rolebox-' + roleId);
    if (box) box.classList.remove('active');
    const badge = document.getElementById('status-' + roleId);
    if (badge) { badge.textContent = '等待'; badge.className = 'status-badge'; }
    const thinking = document.getElementById('thinking-' + roleId);
    if (thinking) thinking.textContent = '';
    const speech = document.getElementById('speech-' + roleId);
    if (speech) speech.textContent = '';
    const details = document.getElementById('details-' + roleId);
    if (details) details.open = false;
  });
  _activeRoleBox = null;
}

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
  badge.classList.remove('thinking', 'speaking', 'done');
  if (status === 'thinking') {
    badge.textContent = '思考中';
    badge.classList.add('thinking');
  } else if (status === 'speaking') {
    badge.textContent = '发言中';
    badge.classList.add('speaking');
  } else if (status === 'done') {
    badge.textContent = '已完成';
    badge.classList.add('done');
  } else {
    badge.textContent = '等待';
  }
}

export function updateAllStatusBadges(debaterStatus) {
  DEBATER_KEYS.forEach(key => {
    const badge = document.getElementById('status-' + key);
    if (!badge) return;
    const order = { waiting: 0, thinking: 1, speaking: 2, done: 3 };
    const curClass = [...badge.classList].find(c => order[c] !== undefined) || 'waiting';
    const backendStatus = debaterStatus[key] || 'waiting';
    if ((order[backendStatus] || 0) >= (order[curClass] || 0)) {
      setBadgeStatus(key, backendStatus);
    }
  });
}

// ── Control Info ──

const PHASE_NAMES = {
  'begin': '准备中',
  'pro_opening': '正方立论',
  'con_opening': '反方立论',
  'con_argument': '反方申论',
  'pro_argument': '正方申论',
  'pro_cross_examine': '正方质询',
  'con_cross_examine': '反方质询',
  'con_cross_summary': '反方质询小结',
  'pro_cross_summary': '正方质询小结',
  'free_debate': '自由辩论',
  'con_closing': '反方总结',
  'pro_closing': '正方总结',
  'verdict': '裁判裁决',
};

export function getPhaseName(phase) {
  return PHASE_NAMES[phase] || phase;
}

// Role label for each (debater, phase) combination shown in the cell header
const ROLE_LABELS = {
  'pro_opening':       { pro_1: '开篇立论' },
  'con_opening':       { con_1: '开篇立论' },
  'con_argument':      { con_2: '申论' },
  'pro_argument':      { pro_2: '申论' },
  'pro_cross_examine': { pro_3: '质询方' },
  'con_cross_examine': { con_3: '质询方' },
  'con_cross_summary': { con_3: '质询小结' },
  'pro_cross_summary': { pro_3: '质询小结' },
  'free_debate':       {},
  'con_closing':       { con_4: '总结陈词' },
  'pro_closing':       { pro_4: '总结陈词' },
};

const PHASE_TO_MODULE = {
  'pro_opening':       'module-opening',
  'con_opening':       'module-opening',
  'con_argument':      'module-argument',
  'pro_argument':      'module-argument',
  'pro_cross_examine': 'module-argument',
  'con_cross_examine': 'module-argument',
  'con_cross_summary': 'module-argument',
  'pro_cross_summary': 'module-argument',
  'free_debate':       null,
  'con_closing':       'module-closing',
  'pro_closing':       'module-closing',
};

export function updateRoleLabel(debater, phase) {
  const roleEl = document.getElementById('role-' + debater);
  if (!roleEl) return;
  const labels = ROLE_LABELS[phase];
  if (labels && labels[debater]) {
    roleEl.textContent = labels[debater];
  }
}

let _activeModule = null;

export function highlightModule(moduleId) {
  if (_activeModule && _activeModule !== moduleId) {
    const prev = document.getElementById(_activeModule);
    if (prev) prev.classList.remove('active-module');
  }
  _activeModule = moduleId;
  if (moduleId) {
    const mod = document.getElementById(moduleId);
    if (mod) mod.classList.add('active-module');
  }
}

export function updateControlInfo(round, totalRounds, phase) {
  const roundInfo = document.getElementById('round-info');
  if (roundInfo) {
    if (round && totalRounds) {
      roundInfo.textContent = '第 ' + round + '/' + totalRounds + ' 轮';
    } else if (totalRounds) {
      roundInfo.textContent = '共 ' + totalRounds + ' 轮';
    }
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
    { id: 'argument',   label: '论证严谨度' },
    { id: 'evidence',   label: '数据与事实支撑' },
    { id: 'rebuttal',   label: '反驳有效性' },
    { id: 'cross',      label: '质询有效性' },
    { id: 'expression', label: '表达清晰度' },
  ];

  dimensionMapping.forEach(({ id, label }) => {
    const proCell = document.getElementById('score-' + id + '-pro');
    const conCell = document.getElementById('score-' + id + '-con');
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
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:9999;';
    document.body.appendChild(container);
  }
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

// ── Cross-Examination Panel ──

export function showCrossPanel(examinerLabel, responderLabel, clear = true) {
  const panel = document.getElementById('cross-examine-panel');
  if (panel) panel.classList.add('visible');
  const examLabel = document.getElementById('cross-examiner-label');
  if (examLabel) examLabel.textContent = examinerLabel;
  const respLabel = document.getElementById('cross-responder-label');
  if (respLabel) respLabel.textContent = responderLabel;
  if (clear) {
    const examSpeeches = document.getElementById('cross-examiner-speeches');
    if (examSpeeches) examSpeeches.innerHTML = '';
    const respSpeeches = document.getElementById('cross-responder-speeches');
    if (respSpeeches) respSpeeches.innerHTML = '';
    const roundBadge = document.getElementById('cross-round-badge');
    if (roundBadge) roundBadge.textContent = '';
  }
}

export function hideCrossPanel() {
  const panel = document.getElementById('cross-examine-panel');
  if (panel) panel.classList.remove('visible');
}

export function appendCrossQ(content, round, examiner) {
  const container = document.getElementById('cross-examiner-speeches');
  if (!container) return;
  const entry = document.createElement('div');
  entry.className = 'cross-q-entry';
  entry.innerHTML =
    '<div class="cross-section-title">' + escapeHtml(examiner) +
    ' <span class="cross-round-badge">第' + round + '轮</span></div>' +
    '<div class="cross-speech">' + escapeHtml(content) + '</div>';
  container.appendChild(entry);
  entry.scrollIntoView({ behavior: 'smooth', block: 'end' });
  const roundBadge = document.getElementById('cross-round-badge');
  if (roundBadge) roundBadge.textContent = '第' + round + '轮';
}

export function appendCrossA(content, round, responder) {
  const container = document.getElementById('cross-responder-speeches');
  if (!container) return;
  const entry = document.createElement('div');
  entry.className = 'cross-q-entry';
  entry.innerHTML =
    '<div class="cross-section-title">' + escapeHtml(responder) +
    ' <span class="cross-round-badge">第' + round + '轮</span></div>' +
    '<div class="cross-speech">' + escapeHtml(content) + '</div>';
  container.appendChild(entry);
  entry.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

// ── Free Debate Panel ──

// Per-side typewriter state for free debate panel.
// Each side (pro/con) gets ONE persistent text box — all debaters on
// that side append to it.  Only reset when showFreePanel or
// resetFreeSpeechEntry is called.
let _freeProSpeechEl = null;
let _freeConSpeechEl = null;

export function showFreePanel() {
  console.log('[DIAG] showFreePanel() called — clearing free panel DOM', new Error().stack);
  const panel = document.getElementById('free-debate-panel');
  if (panel) panel.classList.add('visible');
  const proSpeeches = document.getElementById('free-pro-speeches');
  if (proSpeeches) proSpeeches.innerHTML = '';
  const conSpeeches = document.getElementById('free-con-speeches');
  if (conSpeeches) conSpeeches.innerHTML = '';
  const roundBadge = document.getElementById('free-round-badge');
  if (roundBadge) roundBadge.textContent = '';
  _freeProSpeechEl = null;
  _freeConSpeechEl = null;
}

export function hideFreePanel() {
  const panel = document.getElementById('free-debate-panel');
  if (panel) panel.classList.remove('visible');
}

export function resetFreeSpeechEntry() {
  console.log('[DIAG] resetFreeSpeechEntry() called — nulling _freeProSpeechEl/_freeConSpeechEl', new Error().stack);
  _freeProSpeechEl = null;
  _freeConSpeechEl = null;
}

export function appendFreeSpeechToken(side, content, round) {
  const creatingPro = side === 'pro' && !_freeProSpeechEl;
  const creatingCon = side === 'con' && !_freeConSpeechEl;
  console.log('[DIAG] appendFreeSpeechToken:', side,
    '| contentLen:', content.length,
    '| creatingNew:', creatingPro || creatingCon,
    '| curProLen:', _freeProSpeechEl ? _freeProSpeechEl.textContent.length : 0,
    '| curConLen:', _freeConSpeechEl ? _freeConSpeechEl.textContent.length : 0,
    '| round:', round);
  // Determine which per-side element to use
  if (side === 'pro') {
    if (!_freeProSpeechEl) {
      const container = document.getElementById('free-pro-speeches');
      if (!container) return;
      const entry = document.createElement('div');
      entry.className = 'free-speech-entry';
      entry.innerHTML =
        '<div class="free-speech-debater">正方</div>' +
        '<div class="free-speech"></div>';
      container.appendChild(entry);
      entry.scrollIntoView({ behavior: 'smooth', block: 'end' });
      _freeProSpeechEl = entry.querySelector('.free-speech');
    }
    _freeProSpeechEl.textContent += content;
    _freeProSpeechEl.scrollTop = _freeProSpeechEl.scrollHeight;
  } else {
    if (!_freeConSpeechEl) {
      const container = document.getElementById('free-con-speeches');
      if (!container) return;
      const entry = document.createElement('div');
      entry.className = 'free-speech-entry';
      entry.innerHTML =
        '<div class="free-speech-debater">反方</div>' +
        '<div class="free-speech"></div>';
      container.appendChild(entry);
      entry.scrollIntoView({ behavior: 'smooth', block: 'end' });
      _freeConSpeechEl = entry.querySelector('.free-speech');
    }
    _freeConSpeechEl.textContent += content;
    _freeConSpeechEl.scrollTop = _freeConSpeechEl.scrollHeight;
  }

  // Update round badge when round changes
  const roundBadge = document.getElementById('free-round-badge');
  if (roundBadge && round) {
    const newText = '第' + round + '回合';
    if (roundBadge.textContent !== newText) {
      roundBadge.textContent = newText;
    }
  }
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
