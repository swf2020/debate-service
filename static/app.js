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
    'pro_opening': '正方一辩立论',
    'con_opening': '反方一辩立论',
    'pro_rebuttal': '正方二辩驳论',
    'con_rebuttal': '反方二辩驳论',
    'pro_cross_examine': '正方三辩质询',
    'con_cross_examine': '反方三辩质询',
    'pro_cross_summary': '正方三辩质询小结',
    'con_cross_summary': '反方三辩质询小结',
    'free_debate': '自由辩论',
    'pro_closing': '正方四辩总结',
    'con_closing': '反方四辩总结',
    'verdict': '裁判裁决',
};

const CDWC_PHASES = [
    'pro_opening', 'con_opening', 'pro_rebuttal', 'con_rebuttal',
    'pro_cross_examine', 'con_cross_examine', 'pro_cross_summary', 'con_cross_summary',
    'free_debate', 'con_closing', 'pro_closing'
];

// ── Init ──
document.addEventListener('DOMContentLoaded', () => {
    loadSkills();
    document.getElementById('start-btn').addEventListener('click', startDebate);
    document.getElementById('pause-btn').addEventListener('click', pauseDebate);
    document.getElementById('resume-btn').addEventListener('click', resumeDebate);
    document.getElementById('new-debate-btn').addEventListener('click', resetToNewDebate);

    // Check for active debate on page load (reconnection)
    checkActiveDebate();
});

// ── Reconnection: check for unfinished debate ──
async function checkActiveDebate() {
    try {
        const resp = await fetch('/api/debate/active');
        const data = await resp.json();
        if (data.active && data.debate) {
            const debate = data.debate;
            currentDebateId = debate.id;

            // Hide config, show debate grid
            document.getElementById('debate-grid').style.display = 'grid';
            document.getElementById('control-bar').style.display = 'flex';
            document.getElementById('verdict-section').style.display = 'none';
            document.getElementById('config-panel').style.display = 'none';
            document.getElementById('new-debate-btn').style.display = 'inline-block';

            // Restore control info
            updateControlInfoFromDebate(debate);

            // Restore past speeches into cells
            restoreSpeeches(debate.speeches || []);

            // If debate is finished, show verdict if available
            if (debate.status === 'finished') {
                if (debate.verdict && debate.winner) {
                    showVerdict(debate.verdict, debate.winner);
                }
                document.getElementById('pause-btn').disabled = true;
                document.getElementById('resume-btn').disabled = true;
                return;
            }

            // Connect SSE for live events
            connectSSE(currentDebateId);

            // If debate was paused, set button states
            if (debate.status === 'paused') {
                document.getElementById('pause-btn').disabled = true;
                document.getElementById('resume-btn').disabled = false;
            }
        }
    } catch (err) {
        console.error('Failed to check active debate:', err);
    }
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
    if (debate.format) {
        const formatMap = { cdwc: '新国辩 CDWC', standard: '标准 3v3' };
        document.getElementById('format-info').textContent = formatMap[debate.format] || debate.format;
    }
    if (debate.current_phase) {
        document.getElementById('phase-info').textContent =
            PHASE_NAMES[debate.current_phase] || debate.current_phase;
    }
    updatePhaseProgress(debate.current_phase);
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
    const dimNames = ['论证严谨度', '数据与事实支撑', '反驳有效性', '质询有效性', '表达清晰度'];
    const dimKeys = ['argument', 'evidence', 'rebuttal', 'cross', 'expression'];
    dimKeys.forEach((key, i) => {
        const proCell = document.getElementById(`score-${key}-pro`);
        const conCell = document.getElementById(`score-${key}-con`);
        if (proCell) proCell.textContent = proScores[dimNames[i]] || '-';
        if (conCell) conCell.textContent = conScores[dimNames[i]] || '-';
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

    clearAllCells();

    // Reset buttons
    document.getElementById('pause-btn').disabled = true;
    document.getElementById('resume-btn').disabled = true;
}

// ── Skills ──
async function loadSkills() {
    try {
        const resp = await fetch('/api/skills');
        const data = await resp.json();
        const skills = data.skills || [];

        // Populate all 7 skill selects
        const selects = [
            'pro-skills-1', 'pro-skills-2', 'pro-skills-3', 'pro-skills-4',
            'con-skills-1', 'con-skills-2', 'con-skills-3', 'con-skills-4',
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
    const format = document.getElementById('format-select').value;

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
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                topic,
                format,
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

    eventSource = new EventSource(`/api/debate/${debateId}/stream`);

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

            if (msg.status === 'finished' && msg.verdict) {
                showVerdict(msg.verdict, msg.winner);
                document.getElementById('pause-btn').disabled = true;
                document.getElementById('resume-btn').disabled = true;
            }
            break;

        case 'state_snapshot':
            updateControlInfo(msg.current_round, msg.total_rounds, msg.current_phase);
            if (msg.paused) {
                document.getElementById('pause-btn').disabled = true;
                document.getElementById('resume-btn').disabled = false;
            }
            if (msg.debater_status) {
                for (const [debater, status] of Object.entries(msg.debater_status)) {
                    const statusEl = document.getElementById(`status-${debater}`);
                    if (statusEl) {
                        const statusMap = {
                            'thinking': '思考中...',
                            'speaking': '发言中...',
                            'done': '已完成',
                            'waiting': '等待中',
                        };
                        statusEl.textContent = statusMap[status] || status;
                        statusEl.className = 'status-badge';
                        if (status === 'speaking') statusEl.className += ' active-badge';
                        if (status === 'done') statusEl.className += ' done-badge';
                    }
                }
            }
            if (msg.current_phase) {
                document.getElementById('phase-info').textContent =
                    PHASE_NAMES[msg.current_phase] || msg.current_phase;
                // Update phase progress dots
                updatePhaseProgress(msg.current_phase);
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
            const status = document.getElementById(`status-${msg.debater}`);
            if (status) status.textContent = '发言中...';

            updateControlInfo(msg.round_num, null, msg.phase);

            // Clear thinking/speech for this debater
            const thinkingEl = document.getElementById(`thinking-${msg.debater}`);
            if (thinkingEl) thinkingEl.textContent = '';
            const speechEl = document.getElementById(`speech-${msg.debater}`);
            if (speechEl) speechEl.textContent = '';
            clearRenderQueue(msg.debater);

            updatePhaseProgress(msg.phase);
            // Hide cross-examine panel when entering non-cross phases
            const phaseIsCross = msg.phase === 'pro_cross_examine' || msg.phase === 'con_cross_examine';
            const crossPnl = document.getElementById('cross-examine-panel');
            if (crossPnl && !phaseIsCross) {
                crossPnl.classList.remove('visible');
                document.getElementById('cross-examiner-speeches').innerHTML = '';
                document.getElementById('cross-responder-speeches').innerHTML = '';
            }
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

        case 'cross_q_chunk':
            const crossPanel = document.getElementById('cross-examine-panel');
            if (crossPanel) {
                crossPanel.classList.add('visible');
                document.getElementById('cross-examiner-label').textContent =
                    msg.examiner.replace('pro_', '正方').replace('con_', '反方') + '辩 提问';
                document.getElementById('cross-round-badge').textContent =
                    `第 ${msg.round} 轮`;
                const qDiv = document.createElement('div');
                qDiv.className = 'cross-q-entry';
                qDiv.innerHTML = `<div class="cross-speech" style="border-left:3px solid #4fc3f7;">${msg.content}</div>`;
                document.getElementById('cross-examiner-speeches').appendChild(qDiv);
            }
            break;

        case 'cross_a_chunk':
            const crossP = document.getElementById('cross-examine-panel');
            if (crossP) {
                document.getElementById('cross-responder-label').textContent =
                    msg.responder.replace('pro_', '正方').replace('con_', '反方') + '辩 回答';
                const aDiv = document.createElement('div');
                aDiv.className = 'cross-q-entry';
                aDiv.innerHTML = `<div class="cross-speech" style="border-left:3px solid #ef5350;">${msg.content}</div>`;
                document.getElementById('cross-responder-speeches').appendChild(aDiv);
            }
            break;

        case 'phase_end':
            const endStatus = document.getElementById(`status-${msg.debater}`);
            if (endStatus) endStatus.textContent = '已完成';
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
    const dimNames = ['论证严谨度', '数据与事实支撑', '反驳有效性', '质询有效性', '表达清晰度'];
    const dimKeys = ['argument', 'evidence', 'rebuttal', 'cross', 'expression'];
    dimKeys.forEach((key, i) => {
        const proCell = document.getElementById(`score-${key}-pro`);
        const conCell = document.getElementById(`score-${key}-con`);
        if (proCell) proCell.textContent = proScores[dimNames[i]] || '-';
        if (conCell) conCell.textContent = conScores[dimNames[i]] || '-';
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

    if (phase) {
        updatePhaseProgress(phase);
    }
}

function clearAllCells() {
    ['pro_1', 'pro_2', 'pro_3', 'pro_4', 'con_1', 'con_2', 'con_3', 'con_4'].forEach(key => {
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

function updatePhaseProgress(currentPhase) {
    const bar = document.getElementById('phase-progress');
    if (!bar) return;
    bar.classList.add('visible');
    const idx = CDWC_PHASES.indexOf(currentPhase);
    bar.innerHTML = CDWC_PHASES.map((p, i) => {
        let cls = 'phase-dot';
        if (i < idx) cls += ' done';
        else if (i === idx) cls += ' active';
        return `<span class="${cls}" title="${PHASE_NAMES[p] || p}"></span>`;
    }).join('');
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
        await fetch(`/api/debate/${currentDebateId}/pause`, { method: 'POST' });
    } catch (err) {
        showError('暂停失败: ' + err.message);
    }
}

async function resumeDebate() {
    if (!currentDebateId) return;
    try {
        await fetch(`/api/debate/${currentDebateId}/resume`, { method: 'POST' });
    } catch (err) {
        showError('恢复失败: ' + err.message);
    }
}
