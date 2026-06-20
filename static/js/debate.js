// ── Debate Module ──
// Debate lifecycle: start, SSE connection, pause/resume, state management

import { authHeaders, getToken } from './auth.js';
import { createEventSource } from './api.js';
import { setView, showToast, clearAllCells, highlightSpeaker, setBadgeStatus, updateAllStatusBadges, updateControlInfo, showVerdict, getPhaseName, escapeHtml, DEBATER_KEYS } from './ui.js';
// ── Callback to avoid circular dep with history.js ──
let onBackToList = null;
export function setBackToListCallback(fn) { onBackToList = fn; }

// ── State ──

let currentDebateId = null;
let eventSource = null;
let activeSpeaker = null;

// Typewriter render queue
const renderQueues = {};
let renderTimer = null;
const RENDER_INTERVAL = 25;

// Track which debaters have pending speech chunks
export function hasPendingChunks(debater) {
  const q = renderQueues[debater];
  return q && q.length > 0;
}

function flushRenderQueue() {
  let anyPending = false;
  for (const [key, chunks] of Object.entries(renderQueues)) {
    if (!chunks.length) continue;
    anyPending = true;
    const speakEl = document.getElementById('speech-' + key);
    if (speakEl) {
      speakEl.textContent += chunks.shift();
      speakEl.scrollTop = speakEl.scrollHeight;
    }
  }
  if (anyPending) {
    renderTimer = setTimeout(flushRenderQueue, RENDER_INTERVAL);
  } else {
    renderTimer = null;
    // All render queues empty — mark any pending "finishing" debaters as done
    document.querySelectorAll('.status-badge.finishing').forEach(badge => {
      badge.textContent = '已完成';
      badge.classList.remove('finishing');
      badge.classList.add('done');
    });
  }
}

function enqueueChunk(debater, text) {
  if (!renderQueues[debater]) renderQueues[debater] = [];
  renderQueues[debater].push(text);
  if (!renderTimer) {
    renderTimer = setTimeout(flushRenderQueue, 0);
  }
}

function clearRenderQueue(debater) {
  delete renderQueues[debater];
}

// ── Public API ──

export async function startDebate() {
  const topic = document.getElementById('topic-input').value.trim();
  if (!topic) {
    showToast('请输入辩题', 'error');
    return;
  }

  const rounds = parseInt(document.getElementById('rounds-select').value);

  const proSkills = {
    debater_1: document.getElementById('pro-skills-1').value || null,
    debater_2: document.getElementById('pro-skills-2').value || null,
    debater_3: document.getElementById('pro-skills-3').value || null,
  };
  const conSkills = {
    debater_1: document.getElementById('con-skills-1').value || null,
    debater_2: document.getElementById('con-skills-2').value || null,
    debater_3: document.getElementById('con-skills-3').value || null,
  };
  const judgeSkill = document.getElementById('judge-skill').value || null;

  try {
    const resp = await fetch('/api/debate/start', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ topic, rounds, pro_skills: proSkills, con_skills: conSkills, judge_skill: judgeSkill }),
    });

    if (!resp.ok) {
      const err = await resp.json();
      showToast(err.detail || '创建辩论失败', 'error');
      return;
    }

    const data = await resp.json();
    currentDebateId = data.debate_id;

    setView('debate');
    document.getElementById('pause-btn').disabled = false;
    document.getElementById('resume-btn').disabled = true;
    clearAllCells();

    connectSSE(currentDebateId);
  } catch (err) {
    showToast('网络错误: ' + err.message, 'error');
  }
}

export async function enterDebate(debateId, status) {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  currentDebateId = debateId;

  setView('debate');
  clearAllCells();

  if (status === 'finished') {
    // Load full debate for replay
    try {
      const resp = await fetch('/api/debate/' + debateId, { headers: authHeaders() });
      const debate = await resp.json();
      document.getElementById('round-info').textContent = '共 ' + debate.total_rounds + ' 轮';
      document.getElementById('phase-info').textContent = '已完成';
      document.getElementById('pause-btn').disabled = true;
      document.getElementById('resume-btn').disabled = true;
      restoreSpeeches(debate.speeches || []);
      if (debate.verdict && debate.winner) {
        showVerdict(debate.verdict, debate.winner);
      }
      updateAllStatusBadges(debate.debater_status || {});
    } catch (err) {
      showToast('加载辩论失败: ' + err.message, 'error');
    }
  } else {
    document.getElementById('pause-btn').disabled = false;
    document.getElementById('resume-btn').disabled = true;
    connectSSE(debateId);
  }
}

export async function pauseDebate() {
  if (!currentDebateId) return;
  try {
    await fetch('/api/debate/' + currentDebateId + '/pause', {
      method: 'POST',
      headers: authHeaders(),
    });
  } catch (err) {
    showToast('暂停失败: ' + err.message, 'error');
  }
}

export async function resumeDebate() {
  if (!currentDebateId) return;
  try {
    await fetch('/api/debate/' + currentDebateId + '/resume', {
      method: 'POST',
      headers: authHeaders(),
    });
  } catch (err) {
    showToast('恢复失败: ' + err.message, 'error');
  }
}

export function backToList() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  currentDebateId = null;
  activeSpeaker = null;
  if (onBackToList) onBackToList();
}

export function resetToNewDebate() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  currentDebateId = null;
  activeSpeaker = null;
  setView('config');
  clearAllCells();
  document.getElementById('pause-btn').disabled = true;
  document.getElementById('resume-btn').disabled = true;
}

// ── SSE ──

function connectSSE(debateId) {
  if (eventSource) {
    eventSource.close();
  }

  eventSource = createEventSource(
    debateId,
    getToken(),
    handleSSEMessage,
    (err) => { console.error('SSE connection error:', err); }
  );
}

function handleSSEMessage(msg) {
  switch (msg.type) {
    case 'history_replay':
      currentDebateId = msg.debate_id;
      document.getElementById('round-info').textContent =
        '第 ' + (msg.current_round || '?') + '/' + msg.total_rounds + ' 轮';
      document.getElementById('phase-info').textContent =
        getPhaseName(msg.current_phase) || '-';

      if (msg.paused) {
        document.getElementById('pause-btn').disabled = true;
        document.getElementById('resume-btn').disabled = false;
      }

      restoreSpeeches(msg.speeches || []);
      updateAllStatusBadges(msg.debater_status || {});

      if (msg.status === 'finished' && msg.verdict) {
        showVerdict(msg.verdict, msg.winner);
        document.getElementById('pause-btn').disabled = true;
        document.getElementById('resume-btn').disabled = true;
      }
      break;

    case 'state_snapshot':
      updateControlInfo(msg.current_round, msg.total_rounds, msg.current_phase);
      updateAllStatusBadges(msg.debater_status || {});
      if (msg.paused) {
        document.getElementById('pause-btn').disabled = true;
        document.getElementById('resume-btn').disabled = false;
      } else {
        document.getElementById('pause-btn').disabled = false;
        document.getElementById('resume-btn').disabled = true;
      }
      break;

    case 'phase_start':
      if (activeSpeaker) {
        // Don't override "finishing" or if render queue still has content
        const oldBadge = document.getElementById('status-' + activeSpeaker);
        const oldQueue = renderQueues[activeSpeaker];
        const stillRendering = oldQueue && oldQueue.length > 0;
        if (oldBadge && !oldBadge.classList.contains('finishing') && !stillRendering && !oldBadge.classList.contains('speaking')) {
          setBadgeStatus(activeSpeaker, 'done');
        }
      }
      activeSpeaker = msg.debater;
      highlightSpeaker(activeSpeaker);
      setBadgeStatus(activeSpeaker, 'thinking');
      updateControlInfo(msg.round_num, null, msg.phase);

      // Clear thinking/speech for the new speaker
      const thinkingEl = document.getElementById('thinking-' + msg.debater);
      if (thinkingEl) thinkingEl.textContent = '';
      const speechEl = document.getElementById('speech-' + msg.debater);
      if (speechEl) speechEl.textContent = '';
      clearRenderQueue(msg.debater);

      // Ensure the new speaker's details element is closed initially
      const detailsEl = document.getElementById('details-' + msg.debater);
      if (detailsEl) detailsEl.open = false;
      break;

    case 'thinking_chunk':
      const thinkEl = document.getElementById('thinking-' + msg.debater);
      if (thinkEl) {
        thinkEl.textContent += msg.content;
        thinkEl.scrollTop = thinkEl.scrollHeight;
      }
      const detailsEl = document.getElementById('details-' + msg.debater);
      if (detailsEl && !detailsEl.open) {
        detailsEl.open = true;
      }
      break;

    case 'speech_chunk':
      enqueueChunk(msg.debater, msg.content);
      break;

    case 'debater_status_change':
      // Lightweight badge update — only move forward (never backward).
      // waiting -> thinking -> speaking -> done
      {
        const badge = document.getElementById('status-' + msg.debater);
        if (!badge) break;
        const order = { waiting: 0, thinking: 1, speaking: 2, finishing: 3, done: 4 };
        const curClass = [...badge.classList].find(c => order[c] !== undefined) || 'waiting';
        if ((order[msg.status] || 0) >= (order[curClass] || 0)) {
          setBadgeStatus(msg.debater, msg.status);
        }
      }
      break;

    case 'phase_end':
      // Don't set status to "done" immediately — typewriter still running.
      // Instead, mark as "finishing" so state_snapshot won't override it.
      if (activeSpeaker) {
        setBadgeStatus(activeSpeaker, 'finishing');
      }
      break;

    case 'verdict_chunk':
      // msg.scores contains the full verdict dict from backend
      const verdictData = msg.scores || msg;
      if (verdictData.winner) {
        showVerdict(verdictData, verdictData.winner);
      }
      break;

    case 'paused':
      document.getElementById('pause-btn').disabled = true;
      document.getElementById('resume-btn').disabled = false;
      break;

    case 'resumed':
      document.getElementById('pause-btn').disabled = false;
      document.getElementById('resume-btn').disabled = true;
      break;

    case 'debate_end':
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }
      document.getElementById('pause-btn').disabled = true;
      document.getElementById('resume-btn').disabled = true;

      // Flush any remaining typewriter content before marking done
      if (activeSpeaker) {
        // Force flush remaining render queue for current speaker
        const q = renderQueues[activeSpeaker];
        if (q && q.length > 0) {
          const speakEl = document.getElementById('speech-' + activeSpeaker);
          if (speakEl) {
            speakEl.textContent += q.join('');
            speakEl.scrollTop = speakEl.scrollHeight;
          }
          delete renderQueues[activeSpeaker];
        }
        setBadgeStatus(activeSpeaker, 'done');
      }
      // Clear any remaining render queues and mark all debaters done
      for (const key of DEBATER_KEYS) {
        if (key !== activeSpeaker && renderQueues[key] && renderQueues[key].length > 0) {
          const speakEl = document.getElementById('speech-' + key);
          if (speakEl) {
            speakEl.textContent += renderQueues[key].join('');
            speakEl.scrollTop = speakEl.scrollHeight;
          }
        }
        delete renderQueues[key];
        const badge = document.getElementById('status-' + key);
        if (badge && (badge.classList.contains('speaking') || badge.classList.contains('finishing'))) {
          setBadgeStatus(key, 'done');
        }
      }
      activeSpeaker = null;
      clearTimeout(renderTimer);
      renderTimer = null;

      // Fallback: show verdict if verdict_chunk was missed
      if (msg.verdict && msg.verdict.winner) {
        showVerdict(msg.verdict, msg.verdict.winner);
      }
      break;

    case 'error':
      showToast(msg.message, 'error');
      break;
  }
}

function restoreSpeeches(speeches) {
  const byDebater = {};
  speeches.forEach(s => {
    if (!byDebater[s.debater]) byDebater[s.debater] = [];
    byDebater[s.debater].push(s);
  });

  for (const [debater, items] of Object.entries(byDebater)) {
    const speechEl = document.getElementById('speech-' + debater);
    const statusEl = document.getElementById('status-' + debater);

    const fullText = items.map(s => {
      let header = '';
      if (items.length > 1) {
        const phaseName = getPhaseName(s.phase);
        header = '【' + phaseName + ' - 第' + s.round_num + '轮】\n';
      }
      return header + s.content;
    }).join('\n\n');

    if (speechEl) speechEl.textContent = fullText;
    if (statusEl) { statusEl.textContent = '已完成'; statusEl.className = 'status-badge done'; }
  }
}

// ── Check active debate on login ──

export async function checkActiveDebate() {
  try {
    const resp = await fetch('/api/debate/active', { headers: authHeaders() });
    const data = await resp.json();
    if (data.active && data.debate) {
      currentDebateId = data.debate.id;
    }
  } catch (err) {
    console.error('checkActiveDebate failed:', err);
  }
}

// ── Load skills ──

export async function loadSkills() {
  try {
    const resp = await fetch('/api/skills', { headers: authHeaders() });
    const data = await resp.json();
    const skills = data.skills || [];

    const selects = [
      'pro-skills-1', 'pro-skills-2', 'pro-skills-3',
      'con-skills-1', 'con-skills-2', 'con-skills-3',
      'judge-skill',
    ];

    selects.forEach(selectId => {
      const select = document.getElementById(selectId);
      if (!select) return;
      // Only append if not already populated
      if (select.options.length > 1) return;
      skills.forEach(skill => {
        const option = document.createElement('option');
        option.value = skill.name;
        option.textContent = skill.name.replace('-perspective', '');
        select.appendChild(option);
      });
    });
  } catch (err) {
    console.error('Failed to load skills:', err);
  }
}
