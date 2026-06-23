// ── Debate Module ──
// Debate lifecycle: start, SSE connection, pause/resume, state management

import { authHeaders, getToken } from './auth.js';
import { createEventSource, fetchBatchSpeeches } from './api.js';
import { setView, showToast, clearAllCells, clearAllRoleBoxes, highlightSpeaker, setBadgeStatus, setRoleBoxStatus, updateAllStatusBadges, updateControlInfo, showVerdict, getPhaseName, escapeHtml, DEBATER_KEYS, ALL_ROLE_IDS, updateRoleLabel, highlightModule, highlightRoleBox, clearRoleBox } from './ui.js';

// ── Network heartbeat / auto-pause ──

let heartbeatTimer = null;
let heartbeatFailures = 0;
let autoPaused = false;
let pingInFlight = false;
let lastRecoveryToast = -10000; // negative ensures first toast always fires
const HEARTBEAT_NORMAL = 5000;
const HEARTBEAT_FAST = 2000;
const MAX_FAILURES = 3;
const FETCH_TIMEOUT = 5000;
const RECOVERY_DEBOUNCE = 3000;
let heartbeatIntervalMs = HEARTBEAT_NORMAL;

function fetchWithTimeout(url, options, timeoutMs = FETCH_TIMEOUT) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { ...options, signal: controller.signal }).finally(() => clearTimeout(timer));
}

async function heartbeatPing() {
  if (pingInFlight) return;
  pingInFlight = true;
  try {
    const resp = await fetchWithTimeout('/api/debate/active', { headers: authHeaders() });
    if (resp.ok) {
      if (heartbeatFailures > 0 || autoPaused) {
        heartbeatFailures = 0;
        if (autoPaused) {
          onNetworkRecovered();
        }
      }
      heartbeatFailures = 0;
    } else {
      heartbeatFailures++;
    }
  } catch {
    heartbeatFailures++;
  }

  if (heartbeatFailures >= MAX_FAILURES && !autoPaused && currentDebateId) {
    onNetworkLost();
  }
  pingInFlight = false;
  scheduleHeartbeat();
}

function scheduleHeartbeat() {
  if (heartbeatTimer) clearTimeout(heartbeatTimer);
  heartbeatTimer = setTimeout(heartbeatPing, heartbeatIntervalMs);
}

function startHeartbeat() {
  stopHeartbeat();
  heartbeatFailures = 0;
  autoPaused = false;
  heartbeatIntervalMs = HEARTBEAT_NORMAL;
  scheduleHeartbeat();
  // Browser online/offline events for instant detection
  window.addEventListener('offline', onBrowserOffline);
  window.addEventListener('online', onBrowserOnline);
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearTimeout(heartbeatTimer);
    heartbeatTimer = null;
  }
  heartbeatFailures = 0;
  autoPaused = false;
  pingInFlight = false;
  window.removeEventListener('offline', onBrowserOffline);
  window.removeEventListener('online', onBrowserOnline);
}

function accelerateHeartbeat() {
  heartbeatIntervalMs = HEARTBEAT_FAST;
  if (heartbeatTimer) {
    clearTimeout(heartbeatTimer);
    scheduleHeartbeat();
  }
}

function onBrowserOffline() {
  if (currentDebateId && !autoPaused) {
    // Trigger immediate check — heartbeatPing will fail with timeout in 5s
    heartbeatIntervalMs = HEARTBEAT_FAST;
    heartbeatFailures = Math.max(heartbeatFailures, 1); // count this as 1 failure already
    if (heartbeatTimer) { clearTimeout(heartbeatTimer); scheduleHeartbeat(); }
  }
}

function onBrowserOnline() {
  if (autoPaused) {
    // Immediately try to ping to confirm recovery
    heartbeatPing();
  }
}

async function onNetworkLost() {
  autoPaused = true;
  showToast('网络中断，辩论已自动暂停', 'warning');
  // Update buttons immediately — don't wait for pause API (network is down)
  const pauseBtn = document.getElementById('pause-btn');
  const resumeBtn = document.getElementById('resume-btn');
  if (pauseBtn) pauseBtn.disabled = true;
  if (resumeBtn) resumeBtn.disabled = false;
  // Best-effort pause — may fail if network is fully down
  try {
    await fetchWithTimeout('/api/debate/' + currentDebateId + '/pause', {
      method: 'POST',
      headers: authHeaders(),
    }, 3000);
  } catch {
    // Expected — network is down
  }
}

function onNetworkRecovered() {
  autoPaused = false;
  heartbeatIntervalMs = HEARTBEAT_NORMAL;
  // Debounce recovery toasts
  const now = Date.now();
  if (now - lastRecoveryToast > RECOVERY_DEBOUNCE) {
    lastRecoveryToast = now;
    showToast('网络已恢复', 'success');
  }
  if (currentDebateId) {
    connectSSE(currentDebateId);
  }
}
// ── Callback to avoid circular dep with history.js ──
let onBackToList = null;
export function setBackToListCallback(fn) { onBackToList = fn; }

// ── Frontend speech cache (preloaded on history page load) ──

const speechCache = new Map();

export function getCachedSpeeches(debateId) {
  return speechCache.get(debateId) || null;
}

export function setCachedSpeeches(debateId, speeches) {
  speechCache.set(debateId, speeches);
}

export function clearCachedSpeeches(debateId) {
  speechCache.delete(debateId);
}

// ── State ──

let currentDebateId = null;
let eventSource = null;
let activeSpeaker = null;
let activeRoleId = null;
let currentPhase = '';
let currentCrossPhase = '';
export let inFreeDebate = false;
export let freeDebateRound = 0;
export let freeCurrentSpeaker = '';

// Getter/setter for test compatibility (vitest CJS transform breaks export let live bindings)
export function getInFreeDebate() { return inFreeDebate; }
export function setInFreeDebate(v) { inFreeDebate = v; }
export function getFreeDebateRound() { return freeDebateRound; }
export function setFreeDebateRound(v) { freeDebateRound = v; }
export function getFreeCurrentSpeaker() { return freeCurrentSpeaker; }
export function setFreeCurrentSpeaker(v) { freeCurrentSpeaker = v; }

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

  const proSkills = {
    debater_1: document.getElementById('pro-skills-1').value || null,
    debater_2: document.getElementById('pro-skills-2').value || null,
    debater_3: document.getElementById('pro-skills-3').value || null,
    debater_4: document.getElementById('pro-skills-4').value || null,
  };
  const conSkills = {
    debater_1: document.getElementById('con-skills-1').value || null,
    debater_2: document.getElementById('con-skills-2').value || null,
    debater_3: document.getElementById('con-skills-3').value || null,
    debater_4: document.getElementById('con-skills-4').value || null,
  };
  const judgeSkill = document.getElementById('judge-skill').value || null;

  try {
    const resp = await fetch('/api/debate/start', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ topic, rounds: 1, pro_skills: proSkills, con_skills: conSkills, judge_skill: judgeSkill }),
    });

    if (!resp.ok) {
      const err = await resp.json();
      showToast(err.detail || '创建辩论失败', 'error');
      return;
    }

    const data = await resp.json();
    currentDebateId = data.debate_id;
    window.location.hash = '#/debate/' + data.debate_id;

    setView('debate');
    document.getElementById('pause-btn').disabled = false;
    document.getElementById('resume-btn').disabled = true;
    clearAllCells();

    connectSSE(currentDebateId);
    startHeartbeat();
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
  activeRoleId = null;
  currentPhase = '';

  setView('debate');
  clearAllCells();
  clearAllRoleBoxes();

  if (status === 'finished') {
    // Try frontend memory cache first (preloaded on history page)
    let cached = getCachedSpeeches(debateId);

    if (cached) {
      // Instant render from cache — no network request
      const roundInfo = document.getElementById('round-info');
      if (roundInfo) roundInfo.textContent = '共 ' + (cached.total_rounds || 1) + ' 轮';
      const phaseInfo = document.getElementById('phase-info');
      if (phaseInfo) phaseInfo.textContent = '已完成';
      document.getElementById('pause-btn').disabled = true;
      document.getElementById('resume-btn').disabled = true;
      restoreSpeeches(cached.speeches || []);
      if (cached.verdict && cached.winner) {
        showVerdict(cached.verdict, cached.winner);
      }
      updateAllStatusBadges(cached.debater_status || {});
    } else {
      // Cache miss — fetch from API, showing loading state
      const grid = document.getElementById('debate-grid');
      if (grid) grid.classList.add('loading');
      try {
        const resp = await fetch('/api/debate/' + debateId, { headers: authHeaders() });
        if (!resp.ok) throw new Error('辩论不存在或无权访问');
        const debate = await resp.json();
        // Cache for next time
        setCachedSpeeches(debateId, debate);
        const roundInfo = document.getElementById('round-info');
        if (roundInfo) roundInfo.textContent = '共 ' + debate.total_rounds + ' 轮';
        const phaseInfo = document.getElementById('phase-info');
        if (phaseInfo) phaseInfo.textContent = '已完成';
        document.getElementById('pause-btn').disabled = true;
        document.getElementById('resume-btn').disabled = true;
        restoreSpeeches(debate.speeches || []);
        if (debate.verdict && debate.winner) {
          showVerdict(debate.verdict, debate.winner);
        }
        updateAllStatusBadges(debate.debater_status || {});
      } catch (err) {
        showToast('加载辩论失败: ' + err.message, 'error');
        window.location.hash = '#/';
        return;
      } finally {
        if (grid) grid.classList.remove('loading');
      }
    }
  } else {
    document.getElementById('pause-btn').disabled = false;
    document.getElementById('resume-btn').disabled = true;
    connectSSE(debateId);
    startHeartbeat();
  }

  window.location.hash = '#/debate/' + debateId;
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
  stopHeartbeat();
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  currentDebateId = null;
  activeSpeaker = null;
  activeRoleId = null;
  currentPhase = '';
  currentCrossPhase = '';
  inFreeDebate = false;
  freeDebateRound = 0;
  freeCurrentSpeaker = '';
  window.location.hash = '#/';
  if (onBackToList) onBackToList();
}

export function resetToNewDebate() {
  stopHeartbeat();
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  currentDebateId = null;
  activeSpeaker = null;
  activeRoleId = null;
  currentPhase = '';
  currentCrossPhase = '';
  inFreeDebate = false;
  freeDebateRound = 0;
  freeCurrentSpeaker = '';
  window.location.hash = '#/';
  setView('config');
  clearAllCells();
  clearAllRoleBoxes();
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
    (err) => {
      console.error('SSE connection error:', err);
      accelerateHeartbeat();
    }
  );
}

function handleSSEMessage(msg) {
  switch (msg.type) {
    case 'history_replay':
      currentDebateId = msg.debate_id;
      const roundInfo2 = document.getElementById('round-info');
      if (roundInfo2) roundInfo2.textContent =
        '第 ' + (msg.current_round || '?') + '/' + msg.total_rounds + ' 轮';
      document.getElementById('phase-info').textContent =
        getPhaseName(msg.current_phase) || '-';

      if (msg.paused) {
        document.getElementById('pause-btn').disabled = true;
        document.getElementById('resume-btn').disabled = false;
      }

      restoreSpeeches(msg.speeches || []);
      updateAllStatusBadges(msg.debater_status || {});

      // Override restoreSpeeches statuses: active speakers get real status,
      // waiting debaters get reset to "等待" instead of "已完成"
      if (msg.debater_status && msg.current_phase) {
        for (const [debater, status] of Object.entries(msg.debater_status)) {
          let rPhase = msg.current_phase;
          if (rPhase.endsWith('_response')) {
            // Keep response phase for cross-examination targets
          }
          const rId = debater + ':' + rPhase;
          if (status === 'speaking' || status === 'thinking') {
            setRoleBoxStatus(rId, status);
            activeRoleId = rId;
            currentPhase = msg.current_phase;
            highlightRoleBox(activeRoleId);
          } else if (status === 'waiting') {
            setRoleBoxStatus(rId, 'waiting');
          }
        }
      }

      // Restore free debate state on reconnect
      if (msg.current_phase === 'free_debate') {
        inFreeDebate = true;
        freeDebateRound = 0;
        restoreFreeDebateSpeeches(msg.speeches || []);
      }

      if (msg.status === 'finished' && msg.verdict) {
        showVerdict(msg.verdict, msg.winner);
        document.getElementById('pause-btn').disabled = true;
        document.getElementById('resume-btn').disabled = true;
      }
      break;

    case 'state_snapshot':
      updateControlInfo(msg.current_round, msg.total_rounds, msg.current_phase);
      // Update role box statuses from debater_status
      if (msg.debater_status && activeRoleId) {
        const debaterStatus = msg.debater_status;
        // Map debater keys to role_ids for current phase
        for (const [debater, status] of Object.entries(debaterStatus)) {
          let rPhase = msg.current_phase || currentPhase;
          if (msg.cross_examine_target && debater === msg.cross_examine_target) {
            rPhase = rPhase + '_response';
          }
          const rId = debater + ':' + rPhase;
          const badge = document.getElementById('status-' + rId);
          if (badge && !badge.classList.contains('speaking')) {
            setRoleBoxStatus(rId, status);
          }
        }
      }
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
      {
        const roleId = msg.role_id || (msg.debater + ':' + msg.phase);
        console.log('[DIAG] phase_start | phase:', msg.phase, '| debater:', msg.debater,
          '| role_id:', roleId, '| inFreeDebate:', inFreeDebate);

        // Track cross-examine phase for cross_a_chunk routing
        if (msg.phase === 'pro_cross_examine' || msg.phase === 'con_cross_examine') {
          currentCrossPhase = msg.phase;
        }

        // Handle free debate state tracking
        if (msg.phase === 'free_debate') {
          if (!inFreeDebate) {
            inFreeDebate = true;
            freeDebateRound = 0;
          }
          highlightModule('module-free-debate');
        } else {
          if (inFreeDebate) {
            inFreeDebate = false;
          }
        }

        // Mutual exclusion: mark ALL role boxes in thinking/speaking as done
        document.querySelectorAll('.status-badge.thinking, .status-badge.speaking').forEach(badge => {
          const rid = badge.id.replace('status-', '');
          setRoleBoxStatus(rid, 'done');
        });
        activeRoleId = roleId;
        activeSpeaker = msg.debater;
        currentPhase = msg.phase;
        updateControlInfo(msg.round_num, null, msg.phase);

        // Highlight module and role box for non-free-debate phases
        if (msg.phase !== 'free_debate') {
          highlightModule(
            msg.phase === 'pro_opening' || msg.phase === 'con_opening' ? 'module-opening' :
            msg.phase === 'con_closing' || msg.phase === 'pro_closing' ? 'module-closing' :
            'module-argument'
          );
        }

        // Prepare role box for new speaker
        // Skip clearRoleBox for _response phases — responder boxes accumulate Q&A content
        if (!msg.phase.endsWith('_response')) {
          clearRoleBox(roleId);
        }
        setRoleBoxStatus(roleId, 'thinking');
        highlightRoleBox(roleId);
        clearRenderQueue(roleId);
      }
      break;

    case 'thinking_chunk':
      {
        const tRoleId = msg.role_id || (msg.debater + ':' + (msg.phase || currentPhase));
        let thinkEl = document.getElementById('thinking-' + tRoleId);
        // Fallback to legacy debater element
        if (!thinkEl) thinkEl = document.getElementById('thinking-' + msg.debater);
        if (thinkEl) {
          thinkEl.textContent += msg.content;
          thinkEl.scrollTop = thinkEl.scrollHeight;
        }
        const detailsEl = document.getElementById('details-' + tRoleId) || document.getElementById('details-' + msg.debater);
        if (detailsEl) {
          const summary = detailsEl.querySelector('summary');
          if (summary) summary.textContent = '思考中...';
        }
      }
      break;

    case 'speech_chunk':
      {
        const sRoleId = msg.role_id || (msg.debater + ':' + (msg.phase || currentPhase));
        if (inFreeDebate) {
          const side = msg.debater.startsWith('pro') ? 'pro' : 'con';
          if (side === 'pro' && msg.debater !== freeCurrentSpeaker) freeDebateRound++;
          freeCurrentSpeaker = msg.debater;
          console.log('[DIAG] speech_chunk in free_debate | debater:', msg.debater,
            '| role_id:', sRoleId, '| round:', freeDebateRound,
            '| contentPreview:', msg.content.substring(0, 30));
          enqueueChunk(sRoleId, msg.content);
        } else {
          // Route to role_id box; fall back to debater cell for backward compat
          const roleBoxExists = document.getElementById('speech-' + sRoleId);
          if (roleBoxExists) {
            enqueueChunk(sRoleId, msg.content);
          } else {
            enqueueChunk(msg.debater, msg.content);
          }
        }
      }
      break;

    case 'cross_q_chunk':
      {
        // Route to examiner's role box
        const qPhase = msg.examiner.startsWith('pro') ? 'pro_cross_examine' : 'con_cross_examine';
        const qRoleId = msg.examiner + ':' + qPhase;
        const qSpeech = document.getElementById('speech-' + qRoleId);
        if (qSpeech) {
          // Only add round separator — content already streamed via speech_chunk
          const prefix = '【第' + msg.round + '轮】';
          if (!qSpeech.textContent.includes(prefix)) {
            qSpeech.textContent += (qSpeech.textContent ? '\n\n' : '') + prefix + '\n';
          }
          qSpeech.scrollTop = qSpeech.scrollHeight;
        }
      }
      break;

    case 'cross_a_chunk':
      {
        // Route to responder's role box — prefer explicit role_id from backend
        const aRoleId = msg.role_id ||
          (currentCrossPhase ? msg.responder + ':' + currentCrossPhase + '_response' : msg.responder + ':pro_cross_examine_response');
        const aSpeech = document.getElementById('speech-' + aRoleId);
        if (aSpeech) {
          // Add round separator — content already streamed via speech_chunk
          const prefix = '【第' + msg.round + '轮】';
          if (!aSpeech.textContent.includes(prefix)) {
            const sepSpan = document.createElement('span');
            sepSpan.className = 'cross-round-sep';
            sepSpan.textContent = prefix + ' ';
            aSpeech.appendChild(sepSpan);
          }
        }
      }
      break;

    case 'debater_status_change':
      {
        const dRoleId = activeRoleId || (msg.debater + ':' + (msg.phase || currentPhase));
        const badge = document.getElementById('status-' + dRoleId);
        if (!badge) break;
        const order = { waiting: 0, thinking: 1, speaking: 2, done: 3 };
        const curClass = [...badge.classList].find(c => order[c] !== undefined) || 'waiting';
        if ((order[msg.status] || 0) >= (order[curClass] || 0)) {
          setRoleBoxStatus(dRoleId, msg.status);
        }
      }
      break;

    case 'phase_end':
      if (activeRoleId) {
        setRoleBoxStatus(activeRoleId, 'done');
        const detailsEl = document.getElementById('details-' + activeRoleId);
        if (detailsEl) {
          const summary = detailsEl.querySelector('summary');
          if (summary) summary.textContent = '思考过程';
        }
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
      stopHeartbeat();
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }
      document.getElementById('pause-btn').disabled = true;
      document.getElementById('resume-btn').disabled = true;

      // Flush remaining render queue for active role box
      if (activeRoleId) {
        const q = renderQueues[activeRoleId];
        if (q && q.length > 0) {
          const speakEl = document.getElementById('speech-' + activeRoleId);
          if (speakEl) {
            speakEl.textContent += q.join('');
            speakEl.scrollTop = speakEl.scrollHeight;
          }
          delete renderQueues[activeRoleId];
        }
        setRoleBoxStatus(activeRoleId, 'done');
      }
      // Flush all remaining render queues and mark all role boxes done
      for (const roleId of ALL_ROLE_IDS) {
        if (roleId !== activeRoleId && renderQueues[roleId] && renderQueues[roleId].length > 0) {
          const speakEl = document.getElementById('speech-' + roleId);
          if (speakEl) {
            speakEl.textContent += renderQueues[roleId].join('');
            speakEl.scrollTop = speakEl.scrollHeight;
          }
        }
        delete renderQueues[roleId];
        const badge = document.getElementById('status-' + roleId);
        if (badge) {
          setRoleBoxStatus(roleId, 'done');
        }
      }
      activeRoleId = null;
      activeSpeaker = null;
      inFreeDebate = false;
      freeDebateRound = 0;
      freeCurrentSpeaker = '';
      clearTimeout(renderTimer);
      renderTimer = null;

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
  // Group by role_id (debater:phase), fallback to debater-only grouping
  const byRoleId = {};
  const byDebater = {};

  speeches.forEach(s => {
    const roleId = s.role_id || (s.debater + ':' + s.phase);
    if (!byRoleId[roleId]) byRoleId[roleId] = [];
    byRoleId[roleId].push(s);
    // Also group by debater for legacy cell support
    if (!byDebater[s.debater]) byDebater[s.debater] = [];
    byDebater[s.debater].push(s);
  });

  // Restore to role_id-based boxes
  for (const [roleId, items] of Object.entries(byRoleId)) {
    const speechEl = document.getElementById('speech-' + roleId);
    const thinkingEl = document.getElementById('thinking-' + roleId);
    const statusEl = document.getElementById('status-' + roleId);

    const fullText = items.map(s => s.content).join('\n\n');
    const fullThinking = items.map(s => s.thinking || '').filter(Boolean).join('\n\n');

    if (speechEl) speechEl.textContent = fullText;
    if (thinkingEl && fullThinking) thinkingEl.textContent = fullThinking;
    if (statusEl && (fullText || fullThinking)) { statusEl.textContent = '已完成'; statusEl.className = 'status-badge done'; }
  }

  // Also restore to legacy debater cells for backward compat
  for (const [debater, items] of Object.entries(byDebater)) {
    const speechEl = document.getElementById('speech-' + debater);
    const thinkingEl = document.getElementById('thinking-' + debater);
    const statusEl = document.getElementById('status-' + debater);

    if (speechEl && !speechEl.textContent) {
      const fullText = items.map(s => {
        let header = '';
        if (items.length > 1) {
          const phaseName = getPhaseName(s.phase);
          header = '【' + phaseName + ' - 第' + s.round_num + '轮】\n';
        }
        return header + s.content;
      }).join('\n\n');

      const fullThinking = items.map(s => s.thinking || '').filter(Boolean).join('\n\n');
      speechEl.textContent = fullText;
      if (thinkingEl && fullThinking) thinkingEl.textContent = fullThinking;
    }
    if (statusEl && (fullText || fullThinking)) { statusEl.textContent = '已完成'; statusEl.className = 'status-badge done'; }
  }
}

function restoreFreeDebateSpeeches(speeches) {
  const freeSpeeches = speeches.filter(s => s.speech_type === 'free_debate');
  if (!freeSpeeches.length) return;

  freeSpeeches.sort((a, b) => (a.seq || 0) - (b.seq || 0));

  freeSpeeches.forEach(s => {
    const side = s.debater.startsWith('pro') ? 'pro' : 'con';
    if (side === 'pro' && s.round_num) {
      freeDebateRound = Math.max(freeDebateRound, s.round_num);
    }
    // Route to individual role box
    const roleId = s.role_id || (s.debater + ':free_debate');
    const speechEl = document.getElementById('speech-' + roleId);
    if (speechEl) {
      speechEl.textContent += (speechEl.textContent ? '\n\n' : '') + s.content;
    }
  });
}

// Exported for testing
export { handleSSEMessage, renderQueues, restoreFreeDebateSpeeches, activeRoleId, currentPhase, currentCrossPhase, startHeartbeat, stopHeartbeat, heartbeatPing, fetchWithTimeout, HEARTBEAT_NORMAL, HEARTBEAT_FAST, MAX_FAILURES, FETCH_TIMEOUT };

// ── URL hash routing ──

export function getDebateIdFromHash() {
  const m = window.location.hash.match(/^#\/debate\/(.+)/);
  return m ? m[1] : null;
}

export function isDebateHash() {
  return /^#\/debate\//.test(window.location.hash);
}

// ── Check active debate on login ──

export async function checkActiveDebate() {
  // Skip server check if URL already has a debate hash
  if (isDebateHash()) return null;

  try {
    const resp = await fetch('/api/debate/active', { headers: authHeaders() });
    const data = await resp.json();
    if (data.active && data.debate) {
      currentDebateId = data.debate.id;
      return { id: data.debate.id, status: data.debate.status };
    }
  } catch (err) {
    console.error('checkActiveDebate failed:', err);
  }
  return null;
}

// ── Load skills ──

export async function loadSkills() {
  try {
    const resp = await fetch('/api/skills', { headers: authHeaders() });
    const data = await resp.json();
    const skills = data.skills || [];

    const selects = [
      'pro-skills-1', 'pro-skills-2', 'pro-skills-3', 'pro-skills-4',
      'con-skills-1', 'con-skills-2', 'con-skills-3', 'con-skills-4',
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
