// ── History Module ──
// Date-grouped accordion rendering for debate history

import { authHeaders } from './auth.js';
import { setView, showToast, escapeHtml, formatTime, updateAllStatusBadges, showVerdict, getPhaseName, clearAllCells, highlightSpeaker } from './ui.js';
import { enterDebate } from './debate.js';

// ── Date grouping ──

function groupByDate(debates) {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterdayStart = new Date(todayStart.getTime() - 86400000);
  const dayOfWeek = todayStart.getDay();
  const daysSinceMonday = dayOfWeek === 0 ? 6 : dayOfWeek - 1;
  const thisWeekStart = new Date(todayStart.getTime() - daysSinceMonday * 86400000);
  const lastWeekStart = new Date(thisWeekStart.getTime() - 7 * 86400000);

  const groups = {};
  debates.forEach(d => {
    const date = new Date(d.created_at + 'Z');
    const dateDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    let key;
    if (dateDay >= todayStart) {
      key = '今天';
    } else if (dateDay >= yesterdayStart) {
      key = '昨天';
    } else if (dateDay >= thisWeekStart) {
      key = '本周';
    } else if (dateDay >= lastWeekStart) {
      key = '上周';
    } else {
      key = date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long' });
    }
    if (!groups[key]) groups[key] = [];
    groups[key].push(d);
  });
  return groups;
}

// ── Sorting order ──

const GROUP_ORDER = ['今天', '昨天', '本周', '上周'];

function getSortedGroups(groups) {
  const ordered = [];
  // Known groups first
  GROUP_ORDER.forEach(key => {
    if (groups[key]) ordered.push({ key, debates: groups[key] });
    delete groups[key];
  });
  // Remaining month groups sorted reverse chronologically
  const remaining = Object.keys(groups).sort().reverse();
  remaining.forEach(key => {
    ordered.push({ key, debates: groups[key] });
  });
  return ordered;
}

// ── Load & render ──

export async function loadHistory() {
  try {
    const [debatesResp, activeResp] = await Promise.all([
      fetch('/api/debates', { headers: authHeaders() }),
      fetch('/api/debate/active', { headers: authHeaders() }),
    ]);

    const debatesData = await debatesResp.json();
    const debates = debatesData.debates || [];

    const activeDebates = debates.filter(d => d.status === 'running' || d.status === 'paused');
    const finishedDebates = debates.filter(d => d.status === 'finished');

    setView('history');

    // Active debates section
    renderActiveSection(activeDebates);

    // Finished debates by date
    renderDateGroups(finishedDebates);

    // Empty state
    const emptyEl = document.getElementById('history-empty');
    emptyEl.classList.toggle('hidden', debates.length > 0);
  } catch (err) {
    console.error('Failed to load debate list:', err);
  }
}

function renderActiveSection(debates) {
  const container = document.getElementById('active-debates-section');
  if (debates.length === 0) {
    container.innerHTML = '';
    return;
  }

  let html = '<div class="active-section-label">进行中</div>';
  html += '<div class="date-group expanded active-group">';
  html += '<div class="date-items" style="max-height:none;">';
  debates.forEach(d => {
    const statusLabels = { running: '进行中', paused: '已暂停' };
    const statusLabel = statusLabels[d.status] || d.status;
    html += buildHistoryItem(d, statusLabel);
  });
  html += '</div></div>';
  container.innerHTML = html;
}

function renderDateGroups(finishedDebates) {
  const container = document.getElementById('history-debates-section');
  if (finishedDebates.length === 0) {
    container.innerHTML = '';
    return;
  }

  const groups = groupByDate(finishedDebates);
  const sorted = getSortedGroups(groups);

  let html = '';
  sorted.forEach((group, idx) => {
    const expanded = idx < 2; // "Today" and "Yesterday" expanded by default
    html += '<div class="date-group' + (expanded ? ' expanded' : '') + '">';
    html += '<div class="date-header" onclick="this.parentElement.classList.toggle(\'expanded\')">';
    html += '<span class="date-label">' + group.key + '</span>';
    html += '<span class="date-count">' + group.debates.length + '</span>';
    html += '<span class="chevron">▶</span>';
    html += '</div>';
    html += '<div class="date-items">';
    group.debates.forEach(d => {
      const statusLabels = { finished: '已完成' };
      html += buildHistoryItem(d, '已完成');
    });
    html += '</div></div>';
  });
  container.innerHTML = html;
}

function buildHistoryItem(d, statusLabel) {
  const statusClass = d.status;
  const actionLabel = d.status === 'finished' ? '查看回放' : '进入';
  const winnerMap = { pro: '正方胜', con: '反方胜', draw: '平局' };
  const resultText = d.winner ? ' · ' + (winnerMap[d.winner] || d.winner) : '';
  const timeLabel = formatTime(d.created_at);

  return `
    <div class="history-item">
      <div class="history-item-meta">
        <div class="history-item-topic">${escapeHtml(d.topic)}</div>
        <div class="history-item-info">
          <span>${timeLabel}</span>
          <span>${d.total_rounds}轮</span>
          <span class="history-status ${statusClass}">${statusLabel}${resultText}</span>
        </div>
      </div>
      <div class="history-item-action">
        <button data-debate-id="${d.id}" data-debate-status="${d.status}" class="enter-debate-btn">${actionLabel}</button>
      </div>
    </div>`;
}

export function bindHistoryClicks() {
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.enter-debate-btn');
    if (!btn) return;
    const debateId = btn.dataset.debateId;
    const status = btn.dataset.debateStatus;
    enterDebate(debateId, status);
  });
}

export function showHistoryPanel() {
  // Called by debate.js when returning from debate to list
  loadHistory();
}
