import { describe, it, expect, beforeEach } from 'vitest';

// ── All 22 role_ids from CDWC debate flow ──

const ALL_ROLE_IDS = [
  // Module 1: 立论
  'pro_1:pro_opening',
  'con_1:con_opening',
  // Module 2: 申论与质询
  'con_2:con_argument',
  'pro_2:pro_argument',
  'pro_3:pro_cross_examine',
  'con_2:pro_cross_examine_response',
  'con_3:pro_cross_examine_response',
  'con_3:con_cross_examine',
  'pro_2:con_cross_examine_response',
  'pro_3:con_cross_examine_response',
  'con_3:con_cross_summary',
  'pro_3:pro_cross_summary',
  // Module 3: 自由辩论
  'pro_1:free_debate', 'con_1:free_debate',
  'pro_2:free_debate', 'con_2:free_debate',
  'pro_3:free_debate', 'con_3:free_debate',
  'pro_4:free_debate', 'con_4:free_debate',
  // Module 4: 总结陈词
  'con_4:con_closing',
  'pro_4:pro_closing',
];

// Which module each role_id belongs to
function moduleFor(roleId) {
  const phase = roleId.split(':')[1];
  if (phase === 'pro_opening' || phase === 'con_opening') return 'module-opening';
  if (phase === 'con_closing' || phase === 'pro_closing') return 'module-closing';
  if (phase === 'free_debate') return 'module-free-debate';
  return 'module-argument';
}

// ── Test helpers ──

function buildRoleBox(roleId, debaterName, roleLabel, side) {
  const box = document.createElement('div');
  box.className = `debater-cell role-box ${side}-cell`;
  box.id = `rolebox-${roleId}`;
  box.dataset.roleId = roleId;

  const header = document.createElement('div');
  header.className = 'cell-header';

  const nameDiv = document.createElement('div');
  const nameEl = document.createElement('div');
  nameEl.className = 'cell-debater-name';
  nameEl.textContent = debaterName;
  nameDiv.appendChild(nameEl);

  const roleEl = document.createElement('div');
  roleEl.className = 'cell-role';
  roleEl.textContent = roleLabel;
  nameDiv.appendChild(roleEl);

  const badge = document.createElement('span');
  badge.className = 'status-badge';
  badge.id = `status-${roleId}`;
  badge.textContent = '等待';

  header.appendChild(nameDiv);
  header.appendChild(badge);

  const content = document.createElement('div');
  content.className = 'cell-content';

  const details = document.createElement('details');
  details.id = `details-${roleId}`;
  const summary = document.createElement('summary');
  summary.textContent = '思考过程';
  details.appendChild(summary);
  const thinking = document.createElement('div');
  thinking.className = 'thinking-content';
  thinking.id = `thinking-${roleId}`;
  details.appendChild(thinking);

  const speech = document.createElement('div');
  speech.className = 'speech-content';
  speech.id = `speech-${roleId}`;

  content.appendChild(details);
  content.appendChild(speech);
  box.appendChild(header);
  box.appendChild(content);

  return box;
}

function buildModuleLayout() {
  const grid = document.createElement('div');
  grid.id = 'debate-grid';

  // Module 1: 立论
  const m1 = document.createElement('div');
  m1.className = 'debate-module';
  m1.id = 'module-opening';
  m1.innerHTML = '<div class="module-header">立论环节</div>';
  const b1 = document.createElement('div'); b1.className = 'module-body grid-row';
  b1.appendChild(buildRoleBox('pro_1:pro_opening', '正方一辩', '开篇立论', 'pro'));
  b1.appendChild(buildRoleBox('con_1:con_opening', '反方一辩', '开篇立论', 'con'));
  m1.appendChild(b1); grid.appendChild(m1);

  // Module 2: 申论与质询
  const m2 = document.createElement('div');
  m2.className = 'debate-module';
  m2.id = 'module-argument';
  m2.innerHTML = '<div class="module-header">申论与质询</div>';

  // Row 1: 申论
  const r1 = document.createElement('div'); r1.className = 'module-body grid-row';
  r1.appendChild(buildRoleBox('con_2:con_argument', '反方二辩', '申论', 'con'));
  r1.appendChild(buildRoleBox('pro_2:pro_argument', '正方二辩', '申论', 'pro'));
  m2.appendChild(r1);

  // Row 2: 正方质询 + 反方应答
  const r2 = document.createElement('div'); r2.className = 'module-body grid-row';
  r2.appendChild(buildRoleBox('pro_3:pro_cross_examine', '正方三辩', '质询方', 'pro'));
  r2.appendChild(buildRoleBox('con_2:pro_cross_examine_response', '反方二辩', '应答', 'con'));
  m2.appendChild(r2);

  // Row 3: 反方应答 + 反方质询
  const r3 = document.createElement('div'); r3.className = 'module-body grid-row';
  r3.appendChild(buildRoleBox('con_3:pro_cross_examine_response', '反方三辩', '应答', 'con'));
  r3.appendChild(buildRoleBox('con_3:con_cross_examine', '反方三辩', '质询方', 'con'));
  m2.appendChild(r3);

  // Row 4: 正方应答
  const r4 = document.createElement('div'); r4.className = 'module-body grid-row';
  r4.appendChild(buildRoleBox('pro_2:con_cross_examine_response', '正方二辩', '应答', 'pro'));
  r4.appendChild(buildRoleBox('pro_3:con_cross_examine_response', '正方三辩', '应答', 'pro'));
  m2.appendChild(r4);

  // Row 5: 小结
  const r5 = document.createElement('div'); r5.className = 'module-body grid-row';
  r5.appendChild(buildRoleBox('con_3:con_cross_summary', '反方三辩', '质询小结', 'con'));
  r5.appendChild(buildRoleBox('pro_3:pro_cross_summary', '正方三辩', '质询小结', 'pro'));
  m2.appendChild(r5);

  grid.appendChild(m2);

  // Module 3: 自由辩论
  const m3 = document.createElement('div');
  m3.className = 'debate-module';
  m3.id = 'module-free-debate';
  m3.innerHTML = '<div class="module-header">自由辩论</div>';
  const freePairs = [
    ['pro_1:free_debate', 'con_1:free_debate'],
    ['pro_2:free_debate', 'con_2:free_debate'],
    ['pro_3:free_debate', 'con_3:free_debate'],
    ['pro_4:free_debate', 'con_4:free_debate'],
  ];
  freePairs.forEach(([proId, conId]) => {
    const row = document.createElement('div'); row.className = 'module-body grid-row';
    row.appendChild(buildRoleBox(proId, '正方' + proId.charAt(4) + '辩', '自由辩论', 'pro'));
    row.appendChild(buildRoleBox(conId, '反方' + conId.charAt(4) + '辩', '自由辩论', 'con'));
    m3.appendChild(row);
  });
  grid.appendChild(m3);

  // Module 4: 总结陈词
  const m4 = document.createElement('div');
  m4.className = 'debate-module';
  m4.id = 'module-closing';
  m4.innerHTML = '<div class="module-header">总结陈词</div>';
  const b4 = document.createElement('div'); b4.className = 'module-body grid-row';
  b4.appendChild(buildRoleBox('con_4:con_closing', '反方四辩', '总结陈词', 'con'));
  b4.appendChild(buildRoleBox('pro_4:pro_closing', '正方四辩', '总结陈词', 'pro'));
  m4.appendChild(b4); grid.appendChild(m4);

  document.body.appendChild(grid);
  return grid;
}

function buildAncillaryDOM() {
  // Toast container
  const tc = document.createElement('div'); tc.id = 'toast-container'; document.body.appendChild(tc);
  // Control bar
  const cb = document.createElement('div'); cb.id = 'control-bar'; cb.style.display = 'flex';
  cb.innerHTML = '<span id="round-info"></span><span id="phase-info"></span><button id="pause-btn" disabled></button><button id="resume-btn" disabled></button>';
  document.body.appendChild(cb);
  // Verdict
  const vs = document.createElement('div'); vs.id = 'verdict-section';
  vs.innerHTML = '<div id="verdict-winner"></div><div id="verdict-summary"></div>';
  document.body.appendChild(vs);
  // Cross-examine panel (keep for cross_q/cross_a chunks)
  const cp = document.createElement('div'); cp.id = 'cross-examine-panel';
  cp.innerHTML = '<div class="cross-header">质询阶段</div><div class="cross-body"><div class="cross-examiner-section"><div id="cross-examiner-speeches"></div></div><div class="cross-responder-section"><div id="cross-responder-speeches"></div></div></div>';
  document.body.appendChild(cp);
  // Free debate panel (keep side containers for backward compat)
  const fp = document.createElement('div'); fp.id = 'free-debate-panel';
  fp.innerHTML = '<div class="free-header">自由辩论 <span id="free-round-badge"></span></div><div class="free-body"><div class="free-pro-section"><div id="free-pro-speeches"></div></div><div class="free-con-section"><div id="free-con-speeches"></div></div></div>';
  document.body.appendChild(fp);
}

// ── Module structure tests ──

describe('4-module structure with 22 role boxes', () => {
  beforeEach(() => { document.body.innerHTML = ''; });

  it('has 4 debate-module wrappers', () => {
    buildModuleLayout();
    expect(document.querySelectorAll('#debate-grid .debate-module').length).toBe(4);
  });

  it('module-opening has 2 role boxes', () => {
    buildModuleLayout();
    const mod = document.getElementById('module-opening');
    expect(mod.querySelectorAll('.role-box').length).toBe(2);
  });

  it('module-argument has 10 role boxes', () => {
    buildModuleLayout();
    const mod = document.getElementById('module-argument');
    expect(mod.querySelectorAll('.role-box').length).toBe(10);
  });

  it('module-free-debate has 8 role boxes', () => {
    buildModuleLayout();
    const mod = document.getElementById('module-free-debate');
    expect(mod.querySelectorAll('.role-box').length).toBe(8);
  });

  it('module-closing has 2 role boxes', () => {
    buildModuleLayout();
    const mod = document.getElementById('module-closing');
    expect(mod.querySelectorAll('.role-box').length).toBe(2);
  });

  it('every role_id has speech, thinking, status, details elements', () => {
    buildModuleLayout();
    ALL_ROLE_IDS.forEach(roleId => {
      expect(document.getElementById(`rolebox-${roleId}`), `rolebox-${roleId}`).not.toBeNull();
      expect(document.getElementById(`speech-${roleId}`), `speech-${roleId}`).not.toBeNull();
      expect(document.getElementById(`thinking-${roleId}`), `thinking-${roleId}`).not.toBeNull();
      expect(document.getElementById(`status-${roleId}`), `status-${roleId}`).not.toBeNull();
      expect(document.getElementById(`details-${roleId}`), `details-${roleId}`).not.toBeNull();
    });
  });

  it('each role box has data-role-id attribute', () => {
    buildModuleLayout();
    ALL_ROLE_IDS.forEach(roleId => {
      const box = document.getElementById(`rolebox-${roleId}`);
      expect(box.dataset.roleId).toBe(roleId);
    });
  });
});

// ── Role box management functions ──

describe('highlightRoleBox', () => {
  beforeEach(() => { document.body.innerHTML = ''; buildModuleLayout(); });

  it('adds active class to the correct role box', async () => {
    const { highlightRoleBox } = await import('../ui.js');
    highlightRoleBox('pro_1:pro_opening');
    expect(document.getElementById('rolebox-pro_1:pro_opening').classList.contains('active')).toBe(true);
  });

  it('removes active from previously active box', async () => {
    const { highlightRoleBox } = await import('../ui.js');
    highlightRoleBox('pro_1:pro_opening');
    highlightRoleBox('con_1:con_opening');
    expect(document.getElementById('rolebox-pro_1:pro_opening').classList.contains('active')).toBe(false);
    expect(document.getElementById('rolebox-con_1:con_opening').classList.contains('active')).toBe(true);
  });

  it('handles unknown role_id gracefully', async () => {
    const { highlightRoleBox } = await import('../ui.js');
    expect(() => highlightRoleBox('nobody:nowhere')).not.toThrow();
  });
});

describe('setRoleBoxStatus', () => {
  beforeEach(() => { document.body.innerHTML = ''; buildModuleLayout(); });

  it('sets status badge to 思考中 for thinking', async () => {
    const { setRoleBoxStatus } = await import('../ui.js');
    setRoleBoxStatus('pro_1:pro_opening', 'thinking');
    const badge = document.getElementById('status-pro_1:pro_opening');
    expect(badge.textContent).toBe('思考中');
    expect(badge.classList.contains('thinking')).toBe(true);
  });

  it('sets status badge to 发言中 for speaking', async () => {
    const { setRoleBoxStatus } = await import('../ui.js');
    setRoleBoxStatus('pro_1:pro_opening', 'speaking');
    const badge = document.getElementById('status-pro_1:pro_opening');
    expect(badge.textContent).toBe('发言中');
    expect(badge.classList.contains('speaking')).toBe(true);
  });

  it('sets status badge to 已完成 for done', async () => {
    const { setRoleBoxStatus } = await import('../ui.js');
    setRoleBoxStatus('pro_1:pro_opening', 'done');
    const badge = document.getElementById('status-pro_1:pro_opening');
    expect(badge.textContent).toBe('已完成');
    expect(badge.classList.contains('done')).toBe(true);
  });

  it('sets status badge to 等待 for waiting', async () => {
    const { setRoleBoxStatus } = await import('../ui.js');
    setRoleBoxStatus('pro_1:pro_opening', 'waiting');
    const badge = document.getElementById('status-pro_1:pro_opening');
    expect(badge.textContent).toBe('等待');
    expect(badge.classList.contains('thinking')).toBe(false);
    expect(badge.classList.contains('speaking')).toBe(false);
    expect(badge.classList.contains('done')).toBe(false);
  });
});

describe('clearRoleBox', () => {
  beforeEach(() => { document.body.innerHTML = ''; buildModuleLayout(); });

  it('clears speech and thinking content for a role box', async () => {
    const { clearRoleBox } = await import('../ui.js');
    document.getElementById('speech-pro_1:pro_opening').textContent = 'old speech';
    document.getElementById('thinking-pro_1:pro_opening').textContent = 'old thinking';

    clearRoleBox('pro_1:pro_opening');

    expect(document.getElementById('speech-pro_1:pro_opening').textContent).toBe('');
    expect(document.getElementById('thinking-pro_1:pro_opening').textContent).toBe('');
  });

  it('closes the details element', async () => {
    const { clearRoleBox } = await import('../ui.js');
    document.getElementById('details-pro_1:pro_opening').open = true;

    clearRoleBox('pro_1:pro_opening');

    expect(document.getElementById('details-pro_1:pro_opening').open).toBe(false);
  });
});

// ── Module highlight ──

describe('highlightModule', () => {
  beforeEach(() => { document.body.innerHTML = ''; buildModuleLayout(); });

  it('adds active-module class to specified module', async () => {
    const { highlightModule } = await import('../ui.js');
    highlightModule('module-opening');
    expect(document.getElementById('module-opening').classList.contains('active-module')).toBe(true);
  });

  it('removes active-module from previous module', async () => {
    const { highlightModule } = await import('../ui.js');
    highlightModule('module-opening');
    highlightModule('module-argument');
    expect(document.getElementById('module-opening').classList.contains('active-module')).toBe(false);
    expect(document.getElementById('module-argument').classList.contains('active-module')).toBe(true);
  });
});

// ── SSE routing by role_id ──

describe('SSE routing by role_id', () => {
  beforeEach(async () => {
    document.body.innerHTML = '';
    buildModuleLayout();
    buildAncillaryDOM();
    // Reset state
    const { setInFreeDebate, setFreeDebateRound, setFreeCurrentSpeaker } = await import('../debate.js');
    setInFreeDebate(false);
    setFreeDebateRound(0);
    setFreeCurrentSpeaker('');
  });

  it('phase_start with role_id highlights correct role box', async () => {
    const { handleSSEMessage } = await import('../debate.js');
    handleSSEMessage({
      type: 'phase_start',
      phase: 'pro_opening',
      debater: 'pro_1',
      role_id: 'pro_1:pro_opening',
      round_num: 1,
    });
    const box = document.getElementById('rolebox-pro_1:pro_opening');
    expect(box.classList.contains('active')).toBe(true);
  });

  it('phase_start with role_id highlights correct module', async () => {
    const { handleSSEMessage } = await import('../debate.js');
    handleSSEMessage({
      type: 'phase_start',
      phase: 'con_argument',
      debater: 'con_2',
      role_id: 'con_2:con_argument',
      round_num: 1,
    });
    const mod = document.getElementById('module-argument');
    expect(mod.classList.contains('active-module')).toBe(true);
  });

  it('speech_chunk routes to speech-{role_id}', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage({
      type: 'phase_start',
      phase: 'pro_opening',
      debater: 'pro_1',
      role_id: 'pro_1:pro_opening',
      round_num: 1,
    });

    handleSSEMessage({
      type: 'speech_chunk',
      debater: 'pro_1',
      phase: 'pro_opening',
      role_id: 'pro_1:pro_opening',
      content: '立论内容',
    });

    await new Promise(r => setTimeout(r, 50));
    expect(document.getElementById('speech-pro_1:pro_opening').textContent).toBe('立论内容');
  });

  it('thinking_chunk routes to thinking-{role_id}', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage({
      type: 'phase_start',
      phase: 'pro_opening',
      debater: 'pro_1',
      role_id: 'pro_1:pro_opening',
      round_num: 1,
    });

    handleSSEMessage({
      type: 'thinking_chunk',
      debater: 'pro_1',
      phase: 'pro_opening',
      role_id: 'pro_1:pro_opening',
      content: '我在思考...',
    });

    expect(document.getElementById('thinking-pro_1:pro_opening').textContent).toBe('我在思考...');
  });

  it('speech_chunk for pro_3:pro_cross_summary does NOT write to pro_3:pro_cross_examine box', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    // First, pro_3 speaks in cross-examine
    handleSSEMessage({
      type: 'phase_start',
      phase: 'pro_cross_examine',
      debater: 'pro_3',
      role_id: 'pro_3:pro_cross_examine',
      round_num: 1,
    });
    handleSSEMessage({
      type: 'speech_chunk', debater: 'pro_3', phase: 'pro_cross_examine',
      role_id: 'pro_3:pro_cross_examine', content: '质询内容',
    });
    await new Promise(r => setTimeout(r, 50));

    // Later, pro_3 speaks in cross-summary
    handleSSEMessage({
      type: 'phase_start',
      phase: 'pro_cross_summary',
      debater: 'pro_3',
      role_id: 'pro_3:pro_cross_summary',
      round_num: 1,
    });
    handleSSEMessage({
      type: 'speech_chunk', debater: 'pro_3', phase: 'pro_cross_summary',
      role_id: 'pro_3:pro_cross_summary', content: '小结内容',
    });
    await new Promise(r => setTimeout(r, 50));

    // Each phase has its own box
    expect(document.getElementById('speech-pro_3:pro_cross_examine').textContent).toBe('质询内容');
    expect(document.getElementById('speech-pro_3:pro_cross_summary').textContent).toBe('小结内容');
  });

  it('free debate speech routes to individual debater boxes', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    // Enter free debate
    handleSSEMessage({
      type: 'phase_start',
      phase: 'free_debate',
      debater: 'pro_1',
      role_id: 'pro_1:free_debate',
      round_num: 1,
    });

    handleSSEMessage({
      type: 'speech_chunk',
      debater: 'pro_1',
      phase: 'free_debate',
      role_id: 'pro_1:free_debate',
      content: 'pro_1发言',
    });

    // Different pro debater
    handleSSEMessage({
      type: 'phase_start',
      phase: 'free_debate',
      debater: 'pro_2',
      role_id: 'pro_2:free_debate',
      round_num: 1,
    });

    handleSSEMessage({
      type: 'speech_chunk',
      debater: 'pro_2',
      phase: 'free_debate',
      role_id: 'pro_2:free_debate',
      content: 'pro_2发言',
    });

    await new Promise(r => setTimeout(r, 50));

    // Each debater has their own box
    expect(document.getElementById('speech-pro_1:free_debate').textContent).toBe('pro_1发言');
    expect(document.getElementById('speech-pro_2:free_debate').textContent).toBe('pro_2发言');
  });

  it('cross_q_chunk routes to examiner role box', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage({
      type: 'phase_start',
      phase: 'pro_cross_examine',
      debater: 'pro_3',
      role_id: 'pro_3:pro_cross_examine',
      round_num: 1,
    });

    // Content comes from speech_chunk streaming (not cross_q_chunk)
    handleSSEMessage({
      type: 'speech_chunk',
      debater: 'pro_3',
      phase: 'pro_cross_examine',
      role_id: 'pro_3:pro_cross_examine',
      content: '质询问题',
    });

    handleSSEMessage({
      type: 'cross_q_chunk',
      content: '质询问题',
      round: 1,
      examiner: 'pro_3',
    });

    await new Promise(r => setTimeout(r, 50));
    expect(document.getElementById('speech-pro_3:pro_cross_examine').textContent).toContain('质询问题');
  });

  it('cross_a_chunk adds round separator to responder role box', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage({
      type: 'phase_start',
      phase: 'pro_cross_examine',
      debater: 'pro_3',
      role_id: 'pro_3:pro_cross_examine',
      round_num: 1,
    });

    // Content arrives via speech_chunk
    handleSSEMessage({
      type: 'speech_chunk',
      debater: 'con_2',
      phase: 'pro_cross_examine',
      role_id: 'con_2:pro_cross_examine_response',
      content: '应答内容',
    });
    await new Promise(r => setTimeout(r, 50));

    // cross_a_chunk adds round separator
    handleSSEMessage({
      type: 'cross_a_chunk',
      content: '应答内容',
      round: 1,
      responder: 'con_2',
    });

    const speech = document.getElementById('speech-con_2:pro_cross_examine_response');
    expect(speech.textContent).toContain('应答内容');
    expect(speech.querySelector('.cross-round-sep')).not.toBeNull();
    expect(speech.querySelector('.cross-round-sep').textContent).toContain('第1轮');
  });

  it('backward compat: speech_chunk without role_id falls back to debater', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage({
      type: 'phase_start',
      phase: 'pro_opening',
      debater: 'pro_1',
      round_num: 1,
    });

    handleSSEMessage({
      type: 'speech_chunk',
      debater: 'pro_1',
      content: 'fallback content',
    });

    await new Promise(r => setTimeout(r, 50));
    expect(document.getElementById('speech-pro_1:pro_opening').textContent).toBe('fallback content');
  });

  it('phase_start with cross_examine_response shows module-argument', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage({
      type: 'phase_start',
      phase: 'pro_cross_examine_response',
      debater: 'con_2',
      role_id: 'con_2:pro_cross_examine_response',
      round_num: 1,
    });

    const mod = document.getElementById('module-argument');
    expect(mod.classList.contains('active-module')).toBe(true);
    const box = document.getElementById('rolebox-con_2:pro_cross_examine_response');
    expect(box.classList.contains('active')).toBe(true);
  });

  it('debate_end marks all 22 role boxes as done', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage({ type: 'debate_end', debate_id: 'test', verdict: null });

    ALL_ROLE_IDS.forEach(roleId => {
      const badge = document.getElementById(`status-${roleId}`);
      expect([...badge.classList].some(c => c === 'done' || badge.textContent === '已完成'),
        `status-${roleId} should be done`).toBe(true);
    });
  });

  // ── Free debate role box lifecycle ──

  describe('Free debate role box lifecycle', () => {
    beforeEach(async () => {
      document.body.innerHTML = '';
      buildModuleLayout();
      buildAncillaryDOM();
      const { setInFreeDebate, setFreeDebateRound, setFreeCurrentSpeaker } = await import('../debate.js');
      setInFreeDebate(false);
      setFreeDebateRound(0);
      setFreeCurrentSpeaker('');
    });

    it('free debate phase_start highlights correct role box', async () => {
      const { handleSSEMessage } = await import('../debate.js');
      handleSSEMessage({
        type: 'phase_start',
        phase: 'free_debate',
        debater: 'pro_1',
        role_id: 'pro_1:free_debate',
        round_num: 1,
      });
      const box = document.getElementById('rolebox-pro_1:free_debate');
      expect(box.classList.contains('active')).toBe(true);
    });

    it('free debate phase_start sets new speaker status to 思考中', async () => {
      const { handleSSEMessage } = await import('../debate.js');
      handleSSEMessage({
        type: 'phase_start',
        phase: 'free_debate',
        debater: 'pro_1',
        role_id: 'pro_1:free_debate',
        round_num: 1,
      });
      const badge = document.getElementById('status-pro_1:free_debate');
      expect(badge.textContent).toBe('思考中');
      expect(badge.classList.contains('thinking')).toBe(true);
    });

    it('free debate phase_start marks previous speaker as done', async () => {
      const { handleSSEMessage } = await import('../debate.js');

      // pro_1 speaks
      handleSSEMessage({
        type: 'phase_start', phase: 'free_debate',
        debater: 'pro_1', role_id: 'pro_1:free_debate', round_num: 1,
      });
      handleSSEMessage({
        type: 'speech_chunk', debater: 'pro_1', phase: 'free_debate',
        role_id: 'pro_1:free_debate', content: 'pro_1发言',
      });
      await new Promise(r => setTimeout(r, 50));

      // con_1 speaks next — pro_1 should be marked done
      handleSSEMessage({
        type: 'phase_start', phase: 'free_debate',
        debater: 'con_1', role_id: 'con_1:free_debate', round_num: 2,
      });

      const proBadge = document.getElementById('status-pro_1:free_debate');
      expect(proBadge.textContent).toBe('已完成');
      expect(proBadge.classList.contains('done')).toBe(true);
    });

    it('free debate phase_end sets active role to done', async () => {
      const { handleSSEMessage } = await import('../debate.js');

      handleSSEMessage({
        type: 'phase_start', phase: 'free_debate',
        debater: 'pro_1', role_id: 'pro_1:free_debate', round_num: 1,
      });
      handleSSEMessage({ type: 'phase_end', phase: 'free_debate' });

      const badge = document.getElementById('status-pro_1:free_debate');
      expect(badge.textContent).toBe('已完成');
      expect(badge.classList.contains('done')).toBe(true);
    });

    it('free debate full 8-speaker cycle: all boxes get correct final status', async () => {
      const { handleSSEMessage } = await import('../debate.js');
      const speakers = [
        'pro_1', 'con_1', 'pro_2', 'con_2',
        'pro_3', 'con_3', 'pro_4', 'con_4',
      ];

      for (const debater of speakers) {
        const roleId = debater + ':free_debate';
        handleSSEMessage({
          type: 'phase_start', phase: 'free_debate',
          debater, role_id: roleId, round_num: 1,
        });
        handleSSEMessage({
          type: 'speech_chunk', debater, phase: 'free_debate',
          role_id: roleId, content: debater + '发言',
        });
        await new Promise(r => setTimeout(r, 50));
        handleSSEMessage({ type: 'phase_end', phase: 'free_debate' });
      }

      // All 8 boxes should have done status
      for (const debater of speakers) {
        const roleId = debater + ':free_debate';
        const badge = document.getElementById('status-' + roleId);
        expect(badge.classList.contains('done'),
          `status-${roleId} should be done, got "${badge.textContent}"`
        ).toBe(true);
      }
    });

    it('free debate pro_1 content preserved after pro_2 speaks', async () => {
      const { handleSSEMessage } = await import('../debate.js');

      // pro_1 speaks
      handleSSEMessage({
        type: 'phase_start', phase: 'free_debate',
        debater: 'pro_1', role_id: 'pro_1:free_debate', round_num: 1,
      });
      handleSSEMessage({
        type: 'speech_chunk', debater: 'pro_1', phase: 'free_debate',
        role_id: 'pro_1:free_debate', content: 'pro_1发言内容',
      });
      await new Promise(r => setTimeout(r, 50));

      // con_1 speaks
      handleSSEMessage({
        type: 'phase_start', phase: 'free_debate',
        debater: 'con_1', role_id: 'con_1:free_debate', round_num: 2,
      });
      handleSSEMessage({
        type: 'speech_chunk', debater: 'con_1', phase: 'free_debate',
        role_id: 'con_1:free_debate', content: 'con_1发言内容',
      });
      await new Promise(r => setTimeout(r, 50));

      // pro_2 speaks
      handleSSEMessage({
        type: 'phase_start', phase: 'free_debate',
        debater: 'pro_2', role_id: 'pro_2:free_debate', round_num: 3,
      });
      handleSSEMessage({
        type: 'speech_chunk', debater: 'pro_2', phase: 'free_debate',
        role_id: 'pro_2:free_debate', content: 'pro_2发言内容',
      });
      await new Promise(r => setTimeout(r, 50));

      // pro_1 content intact, pro_2 in its own box
      expect(document.getElementById('speech-pro_1:free_debate').textContent).toBe('pro_1发言内容');
      expect(document.getElementById('speech-pro_2:free_debate').textContent).toBe('pro_2发言内容');
      // con_1's phase_start cleared its own box, so con_1 content is also fine
      expect(document.getElementById('speech-con_1:free_debate').textContent).toBe('con_1发言内容');
    });
  });

  // ── Cross-examination role-box-only rendering ──

  describe('Cross-examination role-box-only rendering', () => {
    beforeEach(async () => {
      document.body.innerHTML = '';
      buildModuleLayout();
      buildAncillaryDOM();
      const { setInFreeDebate, setFreeDebateRound, setFreeCurrentSpeaker } = await import('../debate.js');
      setInFreeDebate(false);
      setFreeDebateRound(0);
      setFreeCurrentSpeaker('');
    });

    it('cross_q_chunk routes to examiner role box, not bottom panel', async () => {
      const { handleSSEMessage } = await import('../debate.js');

      // Start pro_cross_examine phase
      handleSSEMessage({
        type: 'phase_start',
        phase: 'pro_cross_examine',
        debater: 'pro_3',
        role_id: 'pro_3:pro_cross_examine',
        round_num: 1,
      });

      // Content comes from speech_chunk streaming (not cross_q_chunk)
      handleSSEMessage({
        type: 'speech_chunk',
        debater: 'pro_3',
        phase: 'pro_cross_examine',
        role_id: 'pro_3:pro_cross_examine',
        content: '请问反方二辩，你方如何定义"自由"？',
      });

      // cross_q_chunk only adds round separator
      handleSSEMessage({
        type: 'cross_q_chunk',
        examiner: 'pro_3',
        content: '请问反方二辩，你方如何定义"自由"？',
        round: 1,
      });

      await new Promise(r => setTimeout(r, 50));

      // Role box has content from speech_chunk + round prefix from cross_q_chunk
      const roleSpeech = document.getElementById('speech-pro_3:pro_cross_examine');
      expect(roleSpeech.textContent).toContain('请问反方二辩');
      expect(roleSpeech.textContent).toContain('第1轮');

      // Bottom panel stays empty
      const panelContent = document.getElementById('cross-examiner-speeches');
      expect(panelContent.innerHTML).toBe('');
    });

    it('cross_q_chunk dedup: same round prefix added only once', async () => {
      const { handleSSEMessage } = await import('../debate.js');

      // Start pro_cross_examine phase
      handleSSEMessage({
        type: 'phase_start',
        phase: 'pro_cross_examine',
        debater: 'pro_3',
        role_id: 'pro_3:pro_cross_examine',
        round_num: 1,
      });

      // Speech content already set
      handleSSEMessage({
        type: 'speech_chunk',
        debater: 'pro_3',
        phase: 'pro_cross_examine',
        role_id: 'pro_3:pro_cross_examine',
        content: '问题一',
      });
      await new Promise(r => setTimeout(r, 50));

      // First cross_q_chunk adds round separator
      handleSSEMessage({
        type: 'cross_q_chunk',
        examiner: 'pro_3',
        content: '问题一',
        round: 1,
      });

      // Second cross_q_chunk for same round — should NOT duplicate prefix
      handleSSEMessage({
        type: 'cross_q_chunk',
        examiner: 'pro_3',
        content: '问题一续',
        round: 1,
      });

      const roleSpeech = document.getElementById('speech-pro_3:pro_cross_examine');
      const matches = roleSpeech.textContent.match(/第1轮/g);
      expect(matches).not.toBeNull();
      expect(matches.length).toBe(1);
    });

    it('cross_a_chunk adds round separator to responder role box, not bottom panel', async () => {
      const { handleSSEMessage } = await import('../debate.js');

      // Start pro_cross_examine phase (sets currentCrossPhase)
      handleSSEMessage({
        type: 'phase_start',
        phase: 'pro_cross_examine',
        debater: 'pro_3',
        role_id: 'pro_3:pro_cross_examine',
        round_num: 1,
      });

      // speech_chunk streams the answer content
      handleSSEMessage({
        type: 'speech_chunk',
        debater: 'con_2',
        phase: 'pro_cross_examine',
        role_id: 'con_2:pro_cross_examine_response',
        content: '我方认为自由是指...',
      });
      await new Promise(r => setTimeout(r, 50));

      // cross_a_chunk adds round separator only
      handleSSEMessage({
        type: 'cross_a_chunk',
        responder: 'con_2',
        content: '我方认为自由是指...',
        round: 1,
      });

      // Role box has content from speech_chunk + round separator from cross_a_chunk
      const roleSpeech = document.getElementById('speech-con_2:pro_cross_examine_response');
      expect(roleSpeech.textContent).toContain('我方认为自由是指');
      const sep = roleSpeech.querySelector('.cross-round-sep');
      expect(sep).not.toBeNull();
      expect(sep.textContent).toContain('第1轮');

      // Bottom panel stays empty
      const panelContent = document.getElementById('cross-responder-speeches');
      expect(panelContent.innerHTML).toBe('');
    });

    it('state_snapshot with cross_examine_target uses _response suffix for role_id', async () => {
      const { handleSSEMessage } = await import('../debate.js');

      // Start pro_cross_examine with con_2 as target
      handleSSEMessage({
        type: 'phase_start',
        phase: 'pro_cross_examine',
        debater: 'pro_3',
        role_id: 'pro_3:pro_cross_examine',
        round_num: 1,
      });

      handleSSEMessage({
        type: 'state_snapshot',
        debate_id: 'test',
        current_round: 1,
        total_rounds: 1,
        current_phase: 'pro_cross_examine',
        current_debater: 'con_2',
        cross_examine_examiner: 'pro_3',
        cross_examine_target: 'con_2',
        debater_status: { pro_3: 'done', con_2: 'thinking', con_3: 'waiting' },
        paused: false,
      });

      // con_2's badge should use _response suffix
      const con2Badge = document.getElementById('status-con_2:pro_cross_examine_response');
      expect(con2Badge).not.toBeNull();
      expect(con2Badge.classList.contains('thinking') || con2Badge.textContent === '思考中').toBe(true);

      // pro_3's badge uses the examiner phase (no _response)
      const pro3Badge = document.getElementById('status-pro_3:pro_cross_examine');
      expect(pro3Badge).not.toBeNull();
    });

    it('cross_a_chunk with role_id field uses it directly', async () => {
      const { handleSSEMessage } = await import('../debate.js');

      // Send cross_a_chunk with explicit role_id — no phase_start needed
      handleSSEMessage({
        type: 'cross_a_chunk',
        responder: 'pro_2',
        content: '我方反对...',
        round: 2,
        role_id: 'pro_2:con_cross_examine_response',
      });

      const roleSpeech = document.getElementById('speech-pro_2:con_cross_examine_response');
      const sep = roleSpeech.querySelector('.cross-round-sep');
      expect(sep).not.toBeNull();
      expect(sep.textContent).toContain('第2轮');
    });

    it('cross-examination _response phase_start does not clear responder role box', async () => {
      const { handleSSEMessage } = await import('../debate.js');

      // Pre-fill responder's role box with previous answer
      document.getElementById('speech-con_2:pro_cross_examine_response').textContent =
        '第1轮已回答内容';

      // Start pro_cross_examine phase
      handleSSEMessage({
        type: 'phase_start',
        phase: 'pro_cross_examine',
        debater: 'pro_3',
        role_id: 'pro_3:pro_cross_examine',
        round_num: 1,
      });

      // _response phase_start should NOT clear responder box
      handleSSEMessage({
        type: 'phase_start',
        phase: 'pro_cross_examine_response',
        debater: 'con_2',
        role_id: 'con_2:pro_cross_examine_response',
        round_num: 1,
      });

      const roleSpeech = document.getElementById('speech-con_2:pro_cross_examine_response');
      expect(roleSpeech.textContent).toBe('第1轮已回答内容');
    });

    it('pro_2 argument box preserved during cross-examination phases', async () => {
      const { handleSSEMessage } = await import('../debate.js');

      // pro_2 makes argument speech
      handleSSEMessage({
        type: 'phase_start',
        phase: 'pro_argument',
        debater: 'pro_2',
        role_id: 'pro_2:pro_argument',
        round_num: 1,
      });
      handleSSEMessage({
        type: 'speech_chunk',
        debater: 'pro_2',
        phase: 'pro_argument',
        role_id: 'pro_2:pro_argument',
        content: '正方二辩申论内容',
      });
      await new Promise(r => setTimeout(r, 50));

      // Then con_cross_examine starts (pro_2 is a responder)
      handleSSEMessage({
        type: 'phase_start',
        phase: 'con_cross_examine',
        debater: 'con_3',
        role_id: 'con_3:con_cross_examine',
        round_num: 1,
      });

      // pro_2's argument box should still have its content
      const argSpeech = document.getElementById('speech-pro_2:pro_argument');
      expect(argSpeech.textContent).toBe('正方二辩申论内容');

      // pro_2's status badge should be done
      const argBadge = document.getElementById('status-pro_2:pro_argument');
      expect(argBadge.classList.contains('done') || argBadge.textContent === '已完成',
        `pro_2 arg badge expected done, got "${argBadge.textContent}"`).toBe(true);
    });
  });

  // ── Free debate role-box-only rendering ──

  describe('Free debate role-box-only rendering', () => {
    beforeEach(async () => {
      document.body.innerHTML = '';
      buildModuleLayout();
      buildAncillaryDOM();
      const { setInFreeDebate, setFreeDebateRound, setFreeCurrentSpeaker } = await import('../debate.js');
      setInFreeDebate(false);
      setFreeDebateRound(0);
      setFreeCurrentSpeaker('');
    });

    it('free debate speech_chunk does not route to bottom panel', async () => {
      const { handleSSEMessage } = await import('../debate.js');

      // Enter free debate
      handleSSEMessage({
        type: 'phase_start',
        phase: 'free_debate',
        debater: 'pro_1',
        role_id: 'pro_1:free_debate',
        round_num: 1,
      });

      // Send speech_chunk
      handleSSEMessage({
        type: 'speech_chunk',
        debater: 'pro_1',
        phase: 'free_debate',
        role_id: 'pro_1:free_debate',
        content: '自由辩论发言内容',
      });
      await new Promise(r => setTimeout(r, 50));

      // Role box gets content
      const roleSpeech = document.getElementById('speech-pro_1:free_debate');
      expect(roleSpeech.textContent).toContain('自由辩论发言内容');

      // Bottom panel stays empty
      const panelContent = document.getElementById('free-pro-speeches');
      expect(panelContent.innerHTML).toBe('');
    });

    it('free debate panel never gets visible class', async () => {
      const { handleSSEMessage } = await import('../debate.js');

      // Enter free debate
      handleSSEMessage({
        type: 'phase_start',
        phase: 'free_debate',
        debater: 'pro_1',
        role_id: 'pro_1:free_debate',
        round_num: 1,
      });

      const panel = document.getElementById('free-debate-panel');
      expect(panel.classList.contains('visible')).toBe(false);

      // Leave free debate
      handleSSEMessage({
        type: 'phase_start',
        phase: 'con_closing',
        debater: 'con_4',
        role_id: 'con_4:con_closing',
        round_num: 1,
      });

      // Still not visible
      expect(panel.classList.contains('visible')).toBe(false);
    });
  });

  it('clearAllRoleBoxes clears all 22 boxes', async () => {
    const { clearAllRoleBoxes } = await import('../ui.js');

    ALL_ROLE_IDS.forEach(roleId => {
      document.getElementById(`speech-${roleId}`).textContent = 'x';
      document.getElementById(`thinking-${roleId}`).textContent = 'y';
      document.getElementById(`status-${roleId}`).textContent = '发言中';
    });

    clearAllRoleBoxes();

    ALL_ROLE_IDS.forEach(roleId => {
      expect(document.getElementById(`speech-${roleId}`).textContent).toBe('');
      expect(document.getElementById(`thinking-${roleId}`).textContent).toBe('');
    });
  });
});

// ── restoreSpeeches & history_replay ──

describe('restoreSpeeches via history_replay', () => {
  beforeEach(async () => {
    document.body.innerHTML = '';
    buildModuleLayout();
    buildAncillaryDOM();
    const { setInFreeDebate, setFreeDebateRound, setFreeCurrentSpeaker } = await import('../debate.js');
    setInFreeDebate(false);
    setFreeDebateRound(0);
    setFreeCurrentSpeaker('');
  });

  function makeReplay(overrides = {}) {
    return {
      type: 'history_replay',
      debate_id: 'test-001',
      topic: '测试辩题',
      format: 'cdwc',
      total_rounds: 1,
      current_round: 1,
      current_phase: 'pro_opening',
      current_debater: '',
      paused: false,
      status: 'running',
      pro_skills: {},
      con_skills: {},
      judge_skill: null,
      debater_status: {},
      speeches: [],
      ...overrides,
    };
  }

  it('sets status to 已完成 when speech has content', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage(makeReplay({
      debater_status: { pro_1: 'done' },
      speeches: [{
        role_id: 'pro_1:pro_opening',
        debater: 'pro_1',
        phase: 'pro_opening',
        content: '正方开篇立论发言内容',
        thinking: null,
        round_num: 1,
      }],
    }));

    const badge = document.getElementById('status-pro_1:pro_opening');
    expect(badge.textContent).toBe('已完成');
    expect(badge.classList.contains('done')).toBe(true);
  });

  it('does NOT set 已完成 when speech has no content and no thinking', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage(makeReplay({
      debater_status: { pro_1: 'waiting' },
      current_phase: 'pro_opening',
      speeches: [{
        role_id: 'pro_1:pro_opening',
        debater: 'pro_1',
        phase: 'pro_opening',
        content: '',
        thinking: null,
        round_num: 1,
      }],
    }));

    const badge = document.getElementById('status-pro_1:pro_opening');
    // Should NOT be 已完成 (restoreSpeeches skips it because content/thinking empty)
    expect(badge.textContent).not.toBe('已完成');
  });

  it('sets status to 已完成 when speech has thinking but no content', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage(makeReplay({
      debater_status: { pro_1: 'done' },
      speeches: [{
        role_id: 'pro_1:pro_opening',
        debater: 'pro_1',
        phase: 'pro_opening',
        content: '',
        thinking: '需要从定义入手...',
        round_num: 1,
      }],
    }));

    const badge = document.getElementById('status-pro_1:pro_opening');
    expect(badge.textContent).toBe('已完成');
    expect(badge.classList.contains('done')).toBe(true);
  });

  it('activates highlightRoleBox for speaking debater', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage(makeReplay({
      debater_status: { pro_1: 'speaking' },
      current_phase: 'pro_opening',
      speeches: [],
    }));

    const roleBox = document.getElementById('rolebox-pro_1:pro_opening');
    expect(roleBox).not.toBeNull();
    expect(roleBox.classList.contains('active')).toBe(true);
  });

  it('resets waiting debater status to 等待', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage(makeReplay({
      debater_status: { con_1: 'waiting' },
      current_phase: 'pro_opening',
      speeches: [{
        role_id: 'con_1:con_opening',
        debater: 'con_1',
        phase: 'con_opening',
        content: '',
        thinking: null,
        round_num: 1,
      }],
    }));

    const badge = document.getElementById('status-con_1:con_opening');
    expect(badge.textContent).toBe('等待');
  });

  it('handles mixed debater_status: speaking gets highlight, waiting gets 等待, done keeps 已完成', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    // Use free_debate phase where all 8 debaters have role boxes
    handleSSEMessage(makeReplay({
      debater_status: { pro_1: 'speaking', con_1: 'waiting', pro_2: 'done' },
      current_phase: 'free_debate',
      speeches: [
        { role_id: 'pro_1:free_debate', debater: 'pro_1', phase: 'free_debate', content: '自由辩论发言', thinking: null, round_num: 1 },
        { role_id: 'con_1:free_debate', debater: 'con_1', phase: 'free_debate', content: '', thinking: null, round_num: 1 },
        { role_id: 'pro_2:free_debate', debater: 'pro_2', phase: 'free_debate', content: '另一个发言', thinking: null, round_num: 1 },
      ],
    }));

    // pro_1: speaking → highlight active + 发言中
    const box1 = document.getElementById('rolebox-pro_1:free_debate');
    expect(box1.classList.contains('active')).toBe(true);
    const badge1 = document.getElementById('status-pro_1:free_debate');
    expect(badge1.textContent).toBe('发言中');

    // con_1: waiting → 等待
    const badgeCon = document.getElementById('status-con_1:free_debate');
    expect(badgeCon.textContent).toBe('等待');

    // pro_2: done → 已完成 (has content)
    const badge2 = document.getElementById('status-pro_2:free_debate');
    expect(badge2.textContent).toBe('已完成');
  });
});
