// ---- Auth State ----
let currentUser = null;

function getToken() {
    return localStorage.getItem('debate_token');
}

function setToken(token) {
    localStorage.setItem('debate_token', token);
}

function clearToken() {
    localStorage.removeItem('debate_token');
}

// ---- Auth UI ----

function showAuthPanel() {
    document.getElementById('auth-panel').classList.remove('hidden');
    document.getElementById('user-bar').classList.add('hidden');
    document.getElementById('main-content').classList.add('hidden');
}

function showMainUI(user) {
    currentUser = user;
    document.getElementById('auth-panel').classList.add('hidden');
    document.getElementById('user-bar').classList.remove('hidden');
    document.getElementById('main-content').classList.remove('hidden');
    document.getElementById('current-username').textContent = user.username;

    if (user.is_admin) {
        document.getElementById('admin-link').classList.remove('hidden');
    }

    loadSkills();
    loadDebateList();
}

// ---- Auth API ----

async function handleLogin(e) {
    e.preventDefault();
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const errEl = document.getElementById('login-error');
    errEl.textContent = '';

    try {
        const resp = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            errEl.textContent = data.detail || 'Login failed';
            return;
        }
        setToken(data.token);
        showMainUI(data.user);
    } catch (err) {
        errEl.textContent = 'Network error: ' + err.message;
    }
}

async function handleRegister(e) {
    e.preventDefault();
    const username = document.getElementById('register-username').value.trim();
    const password = document.getElementById('register-password').value;
    const errEl = document.getElementById('register-error');
    const succEl = document.getElementById('register-success');
    errEl.textContent = '';
    succEl.textContent = '';

    try {
        const resp = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            errEl.textContent = data.detail || 'Registration failed';
            return;
        }
        succEl.textContent = '注册成功！正在登录...';
        setToken(data.token);
        setTimeout(() => showMainUI(data.user), 500);
    } catch (err) {
        errEl.textContent = 'Network error: ' + err.message;
    }
}

function logout() {
    clearToken();
    currentUser = null;
    if (eventSource) { eventSource.close(); eventSource = null; }
    showAuthPanel();
}

// ---- Auth header helper ----

function authHeaders() {
    const token = getToken();
    return token ? { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' };
}

// ---- State ----
let currentDebateId = null;
let eventSource = null;
let activeSpeaker = null;

// Typewriter render queue: per-debater array of pending chunk strings
const renderQueues = {};
let renderTimer = null;
const RENDER_INTERVAL = 25; // ms between character-group renders

function flushRenderQueue() {
    let anyPending = false;
    for (const [key, chunks] of Object.entries(renderQueues)) {
        if (!chunks.length) continue;
        anyPending = true;
        const speakEl = document.getElementById(`speech-${key}`);
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

// ── Phase name map (shared) ──
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

// ── Init ──
document.addEventListener('DOMContentLoaded', () => {
    // Auth tab switching
    document.querySelectorAll('.auth-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const isLogin = tab.dataset.tab === 'login';
            document.getElementById('login-form').classList.toggle('hidden', !isLogin);
            document.getElementById('register-form').classList.toggle('hidden', isLogin);
        });
    });

    // Debate controls
    document.getElementById('start-btn').addEventListener('click', startDebate);
    document.getElementById('pause-btn').addEventListener('click', pauseDebate);
    document.getElementById('resume-btn').addEventListener('click', resumeDebate);
    document.getElementById('new-debate-btn').addEventListener('click', resetToNewDebate);
    document.getElementById('back-list-btn').addEventListener('click', showHistoryPanel);

    // Check if already logged in
    checkAuth();
});

async function checkAuth() {
    const token = getToken();
    if (!token) {
        showAuthPanel();
        return;
    }

    try {
        const resp = await fetch('/api/auth/me', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (!resp.ok) {
            clearToken();
            showAuthPanel();
            return;
        }
        const data = await resp.json();
        showMainUI(data.user);
    } catch (err) {
        showAuthPanel();
    }
}

// Page load now handled by loadDebateList() — history list is default view.
async function checkActiveDebate() {
    loadDebateList();
}

function restoreSpeeches(speeches) {
    // Group speeches by debater to show all content
    const byDebater = {};
    speeches.forEach(s => {
        if (!byDebater[s.debater]) byDebater[s.debater] = [];
        byDebater[s.debater].push(s);
    });

    for (const [debater, items] of Object.entries(byDebater)) {
        const speechEl = document.getElementById(`speech-${debater}`);
        const statusEl = document.getElementById(`status-${debater}`);

        // Concatenate all speeches for this debater
        const fullText = items.map(s => {
            let header = '';
            if (items.length > 1) {
                const phaseName = PHASE_NAMES[s.phase] || s.phase;
                header = `【${phaseName} - 第${s.round_num}轮】\n`;
            }
            return header + s.content;
        }).join('\n\n');

        if (speechEl) speechEl.textContent = fullText;
        if (statusEl) statusEl.textContent = '已完成';
    }
}

function updateControlInfoFromDebate(debate) {
    if (debate.current_round && debate.total_rounds) {
        document.getElementById('round-info').textContent =
            `第 ${debate.current_round}/${debate.total_rounds} 轮`;
    } else {
        document.getElementById('round-info').textContent =
            `共 ${debate.total_rounds || '?'} 轮`;
    }
    if (debate.current_phase) {
        document.getElementById('phase-info').textContent =
            PHASE_NAMES[debate.current_phase] || debate.current_phase;
    }
}

function showVerdict(verdict, winner) {
    document.getElementById('verdict-section').style.display = 'block';
    const winnerMap = { pro: '正方获胜！', con: '反方获胜！', draw: '平局！' };
    const winnerEl = document.getElementById('verdict-winner');
    winnerEl.textContent = winnerMap[winner] || '结果未知';
    const winnerClassMap = { pro: 'pro-wins', con: 'con-wins', draw: 'draw' };
    winnerEl.className = winnerClassMap[winner] || '';

    // Scores
    const proScores = verdict.pro_scores || {};
    const conScores = verdict.con_scores || {};
    const dimensionKeys = ['argument', 'rebuttal', 'expression', 'teamwork'];
    const dimensions = ['论证严谨度', '数据与事实支撑', '反驳有效性', '表达清晰度'];
    dimensionKeys.forEach((key, i) => {
        const proCell = document.getElementById(`score-${key}-pro`);
        const conCell = document.getElementById(`score-${key}-con`);
        if (proCell) proCell.textContent = proScores[dimensions[i]] || '-';
        if (conCell) conCell.textContent = conScores[dimensions[i]] || '-';
    });
    const proTotal = document.getElementById('score-total-pro');
    const conTotal = document.getElementById('score-total-con');
    if (proTotal) proTotal.textContent = proScores.total || '-';
    if (conTotal) conTotal.textContent = conScores.total || '-';
    document.getElementById('verdict-summary').textContent = verdict.summary || '';
}

function resetToNewDebate() {
    // Disconnect SSE
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    currentDebateId = null;

    // Show config, hide debate
    document.getElementById('config-panel').style.display = 'block';
    document.getElementById('debate-grid').style.display = 'none';
    document.getElementById('control-bar').style.display = 'none';
    document.getElementById('verdict-section').style.display = 'none';
    document.getElementById('new-debate-btn').style.display = 'none';
    document.getElementById('back-list-btn').style.display = 'none';

    clearAllCells();

    // Reset buttons
    document.getElementById('pause-btn').disabled = true;
    document.getElementById('resume-btn').disabled = true;
}

// ── Skills ──
async function loadSkills() {
    try {
        const resp = await fetch('/api/skills', { headers: authHeaders() });
        const data = await resp.json();
        const skills = data.skills || [];

        // Populate all 7 skill selects
        const selects = [
            'pro-skills-1', 'pro-skills-2', 'pro-skills-3',
            'con-skills-1', 'con-skills-2', 'con-skills-3',
            'judge-skill'
        ];

        selects.forEach(selectId => {
            const select = document.getElementById(selectId);
            if (!select) return;
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

// ── Start Debate ──
async function startDebate() {
    const topic = document.getElementById('topic-input').value.trim();
    if (!topic) {
        showError('请输入辩题');
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
            body: JSON.stringify({
                topic,
                rounds,
                pro_skills: proSkills,
                con_skills: conSkills,
                judge_skill: judgeSkill,
            }),
        });

        if (!resp.ok) {
            const err = await resp.json();
            showError(err.detail || '创建辩论失败');
            return;
        }

        const data = await resp.json();
        currentDebateId = data.debate_id;

        // Show debate grid, hide verdict
        document.getElementById('debate-grid').style.display = 'grid';
        document.getElementById('history-panel').style.display = 'none';
        document.getElementById('back-list-btn').style.display = 'inline-block';
        document.getElementById('control-bar').style.display = 'flex';
        document.getElementById('verdict-section').style.display = 'none';
        document.getElementById('config-panel').style.display = 'none';
        document.getElementById('new-debate-btn').style.display = 'inline-block';

        // Clear previous content
        clearAllCells();

        // Connect SSE
        connectSSE(currentDebateId);

    } catch (err) {
        showError('网络错误: ' + err.message);
    }
}

// ── SSE Connection ──
function connectSSE(debateId) {
    if (eventSource) {
        eventSource.close();
    }

    eventSource = new EventSource('/api/debate/' + debateId + '/stream?token=' + encodeURIComponent(getToken()));

    eventSource.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleSSEMessage(msg);
        } catch (err) {
            console.error('SSE parse error:', err);
        }
    };

    eventSource.onerror = (err) => {
        console.error('SSE connection error:', err);
    };
}

// ── SSE Message Handler ──
function handleSSEMessage(msg) {
    switch (msg.type) {
        case 'history_replay':
            // Full state restore on reconnect
            currentDebateId = msg.debate_id;
            document.getElementById('round-info').textContent =
                `第 ${msg.current_round || '?'}/${msg.total_rounds} 轮`;
            document.getElementById('phase-info').textContent =
                PHASE_NAMES[msg.current_phase] || msg.current_phase || '-';

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
            // Highlight active speaker cell
            if (activeSpeaker) {
                const prevCell = document.getElementById(`cell-${activeSpeaker}`);
                if (prevCell) prevCell.classList.remove('active');
                const prevStatus = document.getElementById(`status-${activeSpeaker}`);
                if (prevStatus) prevStatus.textContent = '已完成';
            }
            activeSpeaker = msg.debater;
            const cell = document.getElementById(`cell-${msg.debater}`);
            if (cell) cell.classList.add('active');
            updateControlInfo(msg.round_num, null, msg.phase);

            // Clear thinking/speech for this debater
            const thinkingEl = document.getElementById(`thinking-${msg.debater}`);
            if (thinkingEl) thinkingEl.textContent = '';
            const speechEl = document.getElementById(`speech-${msg.debater}`);
            if (speechEl) speechEl.textContent = '';
            clearRenderQueue(msg.debater);
            break;

        case 'thinking_chunk':
            const thinkEl = document.getElementById(`thinking-${msg.debater}`);
            if (thinkEl) {
                thinkEl.textContent += msg.content;
                thinkEl.scrollTop = thinkEl.scrollHeight;
            }
            const detailsEl = document.getElementById(`details-${msg.debater}`);
            if (detailsEl && !detailsEl.open) {
                detailsEl.open = true;
            }
            break;

        case 'speech_chunk':
            enqueueChunk(msg.debater, msg.content);
            break;

        case 'phase_end':
            break;

        case 'verdict_chunk':
            document.getElementById('verdict-section').style.display = 'block';
            const verdict = msg.scores || msg;
            if (verdict.winner) {
                showVerdict(verdict, verdict.winner);
            } else {
                renderVerdict(verdict);
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
            break;

        case 'error':
            showError(msg.message);
            break;
    }
}

// ── Verdict Rendering ──
function renderVerdict(verdict) {
    const table = document.getElementById('verdict-table');
    const winner = document.getElementById('verdict-winner');
    const summary = document.getElementById('verdict-summary');

    const proScores = verdict.pro_scores || {};
    const conScores = verdict.con_scores || {};
    const dimensions = ['论证严谨度', '数据与事实支撑', '反驳有效性', '表达清晰度'];

    const dimensionKeys = ['argument', 'rebuttal', 'expression', 'teamwork'];
    dimensionKeys.forEach((key, i) => {
        const proCell = document.getElementById(`score-${key}-pro`);
        const conCell = document.getElementById(`score-${key}-con`);
        if (proCell) proCell.textContent = proScores[dimensions[i]] || '-';
        if (conCell) conCell.textContent = conScores[dimensions[i]] || '-';
    });

    const proTotal = document.getElementById('score-total-pro');
    const conTotal = document.getElementById('score-total-con');
    if (proTotal) proTotal.textContent = proScores.total || '-';
    if (conTotal) conTotal.textContent = conScores.total || '-';

    const winnerMap = { pro: '正方获胜！', con: '反方获胜！', draw: '平局！' };
    winner.textContent = winnerMap[verdict.winner] || '结果未知';

    const winnerClassMap = { pro: 'pro-wins', con: 'con-wins', draw: 'draw' };
    winner.className = winnerClassMap[verdict.winner] || '';

    summary.textContent = verdict.summary || '';
}

// ── UI Helpers ──
function updateControlInfo(round, totalRounds, phase) {
    const roundInfo = document.getElementById('round-info');
    if (round && totalRounds) {
        roundInfo.textContent = `第 ${round}/${totalRounds} 轮`;
    }
    if (phase) {
        document.getElementById('phase-info').textContent = PHASE_NAMES[phase] || phase;
    }

    const pauseBtn = document.getElementById('pause-btn');
    const resumeBtn = document.getElementById('resume-btn');
    if (phase && phase !== 'begin' && phase !== 'verdict') {
        pauseBtn.disabled = false;
        resumeBtn.disabled = true;
    }
}

function clearAllCells() {
    ['pro_1', 'pro_2', 'pro_3', 'con_1', 'con_2', 'con_3'].forEach(key => {
        const cell = document.getElementById(`cell-${key}`);
        if (cell) cell.classList.remove('active');
        const status = document.getElementById(`status-${key}`);
        if (status) status.textContent = '等待中';
        const thinking = document.getElementById(`thinking-${key}`);
        if (thinking) thinking.textContent = '';
        const speech = document.getElementById(`speech-${key}`);
        if (speech) speech.textContent = '';
        const details = document.getElementById(`details-${key}`);
        if (details) details.open = false;
        clearRenderQueue(key);
    });
    activeSpeaker = null;
}

// ── History List ──
async function loadDebateList() {
    try {
        const [debatesResp, activeResp] = await Promise.all([
            fetch('/api/debates', { headers: authHeaders() }),
            fetch('/api/debate/active', { headers: authHeaders() }),
        ]);
        const debatesData = await debatesResp.json();
        const debates = debatesData.debates || [];

        const activeDebates = debates.filter(d => d.status === 'running' || d.status === 'paused');
        const historyDebates = debates.filter(d => d.status === 'finished');

        // Show history panel, hide everything else
        document.getElementById('history-panel').style.display = 'block';
        document.getElementById('config-panel').style.display = 'none';
        document.getElementById('debate-grid').style.display = 'none';
        document.getElementById('control-bar').style.display = 'none';
        document.getElementById('verdict-section').style.display = 'none';
        document.getElementById('new-debate-btn').style.display = 'none';
        document.getElementById('back-list-btn').style.display = 'none';

        // Render sections
        renderDebateSection('active-debates-section', '进行中', activeDebates);
        renderDebateSection('history-debates-section', '已完成', historyDebates);

        const emptyEl = document.getElementById('history-empty');
        emptyEl.style.display = debates.length === 0 ? 'block' : 'none';
    } catch (err) {
        console.error('Failed to load debate list:', err);
    }
}

function renderDebateSection(containerId, title, debates) {
    const container = document.getElementById(containerId);
    if (debates.length === 0) {
        container.innerHTML = '';
        return;
    }

    let html = `<div class="history-section-title">${title}</div>`;
    debates.forEach(d => {
        const statusLabels = { running: '进行中', paused: '已暂停', finished: '已完成' };
        const statusClass = d.status;
        const statusLabel = statusLabels[d.status] || d.status;
        const timeLabel = formatTime(d.created_at);
        const actionLabel = d.status === 'finished' ? '查看回放' : '进入';
        const winnerMap = { pro: '正方胜', con: '反方胜', draw: '平局' };
        const resultText = d.winner ? ` · ${winnerMap[d.winner] || d.winner}` : '';

        html += `
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
                    <button onclick="enterDebate('${d.id}', '${d.status}')">${actionLabel}</button>
                </div>
            </div>`;
    });
    container.innerHTML = html;
}

function formatTime(ts) {
    if (!ts) return '';
    try {
        const d = new Date(ts + 'Z');
        const now = new Date();
        const diffMs = now - d;
        const diffMins = Math.floor(diffMs / 60000);
        if (diffMins < 1) return '刚刚';
        if (diffMins < 60) return `${diffMins}分钟前`;
        const diffHours = Math.floor(diffMins / 60);
        if (diffHours < 24) return `${diffHours}小时前`;
        const diffDays = Math.floor(diffHours / 24);
        if (diffDays < 7) return `${diffDays}天前`;
        return d.toLocaleDateString('zh-CN');
    } catch (e) {
        return ts;
    }
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

async function enterDebate(debateId, status) {
    currentDebateId = debateId;

    // Show debate grid
    document.getElementById('history-panel').style.display = 'none';
    document.getElementById('config-panel').style.display = 'none';
    document.getElementById('debate-grid').style.display = 'grid';
    document.getElementById('control-bar').style.display = 'flex';
    document.getElementById('verdict-section').style.display = 'none';
    document.getElementById('new-debate-btn').style.display = 'inline-block';
    document.getElementById('back-list-btn').style.display = 'inline-block';

    clearAllCells();

    if (status === 'finished') {
        // Load full debate data for replay
        try {
            const resp = await fetch(`/api/debate/${debateId}`, { headers: authHeaders() });
            const debate = await resp.json();
            document.getElementById('round-info').textContent = `共 ${debate.total_rounds} 轮`;
            document.getElementById('phase-info').textContent = '已完成';
            document.getElementById('pause-btn').disabled = true;
            document.getElementById('resume-btn').disabled = true;
            restoreSpeeches(debate.speeches || []);
            if (debate.verdict && debate.winner) {
                showVerdict(debate.verdict, debate.winner);
            }
            updateAllStatusBadges(debate.debater_status || {});
        } catch (err) {
            showError('加载辩论失败: ' + err.message);
        }
    } else {
        // Connect SSE for live debate
        document.getElementById('pause-btn').disabled = false;
        document.getElementById('resume-btn').disabled = true;
        connectSSE(debateId);
    }
}

function updateAllStatusBadges(debaterStatus) {
    const allKeys = ['pro_1', 'pro_2', 'pro_3', 'con_1', 'con_2', 'con_3'];
    allKeys.forEach(key => {
        const status = debaterStatus[key] || 'waiting';
        setBadgeStatus(key, status);
    });
}

function setBadgeStatus(debater, status) {
    const badge = document.getElementById(`status-${debater}`);
    if (!badge) return;
    badge.classList.remove('active-badge', 'done-badge');
    if (status === 'speaking') {
        badge.textContent = '发言中';
        badge.classList.add('active-badge');
    } else if (status === 'done') {
        badge.textContent = '已完成';
        badge.classList.add('done-badge');
    } else {
        badge.textContent = '等待中';
    }
}

function showHistoryPanel() {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    currentDebateId = null;
    activeSpeaker = null;
    loadDebateList();
}

function showError(message) {
    const toast = document.getElementById('error-toast');
    if (!toast) return;
    toast.textContent = message;
    toast.style.display = 'block';
    setTimeout(() => { toast.style.display = 'none'; }, 5000);
}

// ── Pause/Resume ──
async function pauseDebate() {
    if (!currentDebateId) return;
    try {
        await fetch(`/api/debate/${currentDebateId}/pause`, { method: 'POST', headers: authHeaders() });
    } catch (err) {
        showError('暂停失败: ' + err.message);
    }
}

async function resumeDebate() {
    if (!currentDebateId) return;
    try {
        await fetch(`/api/debate/${currentDebateId}/resume`, { method: 'POST', headers: authHeaders() });
    } catch (err) {
        showError('恢复失败: ' + err.message);
    }
}
