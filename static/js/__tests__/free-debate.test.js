import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// ── Shared DOM builders (role-box style, matching modules.test.js) ──

const ALL_ROLE_IDS = [
  'pro_1:pro_opening', 'con_1:con_opening',
  'con_2:con_argument', 'pro_2:pro_argument',
  'pro_3:pro_cross_examine', 'con_2:pro_cross_examine_response',
  'con_3:pro_cross_examine_response', 'con_3:con_cross_examine',
  'pro_2:con_cross_examine_response', 'pro_3:con_cross_examine_response',
  'con_3:con_cross_summary', 'pro_3:pro_cross_summary',
  'pro_1:free_debate', 'con_1:free_debate',
  'pro_2:free_debate', 'con_2:free_debate',
  'pro_3:free_debate', 'con_3:free_debate',
  'pro_4:free_debate', 'con_4:free_debate',
  'con_4:con_closing', 'pro_4:pro_closing',
];

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

  // Module 1
  const m1 = document.createElement('div');
  m1.className = 'debate-module'; m1.id = 'module-opening';
  m1.innerHTML = '<div class="module-header">立论环节</div>';
  const b1 = document.createElement('div'); b1.className = 'module-body grid-row';
  b1.appendChild(buildRoleBox('pro_1:pro_opening', '正方一辩', '开篇立论', 'pro'));
  b1.appendChild(buildRoleBox('con_1:con_opening', '反方一辩', '开篇立论', 'con'));
  m1.appendChild(b1); grid.appendChild(m1);

  // Module 2
  const m2 = document.createElement('div');
  m2.className = 'debate-module'; m2.id = 'module-argument';
  m2.innerHTML = '<div class="module-header">申论与质询</div>';
  const r1 = document.createElement('div'); r1.className = 'module-body grid-row';
  r1.appendChild(buildRoleBox('con_2:con_argument', '反方二辩', '申论', 'con'));
  r1.appendChild(buildRoleBox('pro_2:pro_argument', '正方二辩', '申论', 'pro'));
  m2.appendChild(r1);
  const r2 = document.createElement('div'); r2.className = 'module-body grid-row';
  r2.appendChild(buildRoleBox('pro_3:pro_cross_examine', '正方三辩', '质询方', 'pro'));
  r2.appendChild(buildRoleBox('con_2:pro_cross_examine_response', '反方二辩', '应答', 'con'));
  m2.appendChild(r2);
  const r3 = document.createElement('div'); r3.className = 'module-body grid-row';
  r3.appendChild(buildRoleBox('con_3:pro_cross_examine_response', '反方三辩', '应答', 'con'));
  r3.appendChild(buildRoleBox('con_3:con_cross_examine', '反方三辩', '质询方', 'con'));
  m2.appendChild(r3);
  const r4 = document.createElement('div'); r4.className = 'module-body grid-row';
  r4.appendChild(buildRoleBox('pro_2:con_cross_examine_response', '正方二辩', '应答', 'pro'));
  r4.appendChild(buildRoleBox('pro_3:con_cross_examine_response', '正方三辩', '应答', 'pro'));
  m2.appendChild(r4);
  const r5 = document.createElement('div'); r5.className = 'module-body grid-row';
  r5.appendChild(buildRoleBox('con_3:con_cross_summary', '反方三辩', '质询小结', 'con'));
  r5.appendChild(buildRoleBox('pro_3:pro_cross_summary', '正方三辩', '质询小结', 'pro'));
  m2.appendChild(r5);
  grid.appendChild(m2);

  // Module 3
  const m3 = document.createElement('div');
  m3.className = 'debate-module'; m3.id = 'module-free-debate';
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

  // Module 4
  const m4 = document.createElement('div');
  m4.className = 'debate-module'; m4.id = 'module-closing';
  m4.innerHTML = '<div class="module-header">总结陈词</div>';
  const b4 = document.createElement('div'); b4.className = 'module-body grid-row';
  b4.appendChild(buildRoleBox('con_4:con_closing', '反方四辩', '总结陈词', 'con'));
  b4.appendChild(buildRoleBox('pro_4:pro_closing', '正方四辩', '总结陈词', 'pro'));
  m4.appendChild(b4); grid.appendChild(m4);

  document.body.appendChild(grid);
  return grid;
}

function buildAncillaryDOM() {
  const tc = document.createElement('div'); tc.id = 'toast-container'; document.body.appendChild(tc);
  const cb = document.createElement('div'); cb.id = 'control-bar'; cb.style.display = 'flex';
  cb.innerHTML = '<span id="round-info"></span><span id="phase-info"></span><button id="pause-btn" disabled></button><button id="resume-btn" disabled></button>';
  document.body.appendChild(cb);
  const vs = document.createElement('div'); vs.id = 'verdict-section';
  vs.innerHTML = '<div id="verdict-winner"></div><div id="verdict-summary"></div>';
  document.body.appendChild(vs);
  const cp = document.createElement('div'); cp.id = 'cross-examine-panel';
  cp.innerHTML = '<div id="cross-examiner-speeches"></div><div id="cross-responder-speeches"></div>';
  document.body.appendChild(cp);
  const fp = document.createElement('div'); fp.id = 'free-debate-panel';
  fp.innerHTML = '<div id="free-pro-speeches"></div><div id="free-con-speeches"></div><span id="free-round-badge"></span>';
  document.body.appendChild(fp);
}

// ── Mock auth.js ──

vi.mock('../auth.js', () => ({
  authHeaders: () => ({}),
  getToken: () => 'mock-token',
}));

vi.mock('../api.js', () => ({
  createEventSource: vi.fn(),
}));

// ── Panel function tests (functions still exist in ui.js) ──

describe('free debate panel functions', () => {
  beforeEach(() => { document.body.innerHTML = ''; });

  describe('showFreePanel / hideFreePanel', () => {
    it('showFreePanel adds "visible" class to the free debate panel', async () => {
      const { showFreePanel } = await import('../ui.js');
      const fp = document.createElement('div'); fp.id = 'free-debate-panel'; document.body.appendChild(fp);
      showFreePanel();
      expect(fp.classList.contains('visible')).toBe(true);
    });

    it('hideFreePanel removes "visible" class', async () => {
      const { showFreePanel, hideFreePanel } = await import('../ui.js');
      const fp = document.createElement('div'); fp.id = 'free-debate-panel'; document.body.appendChild(fp);
      showFreePanel();
      hideFreePanel();
      expect(fp.classList.contains('visible')).toBe(false);
    });

    it('showFreePanel clears previous pro speeches', async () => {
      const { showFreePanel } = await import('../ui.js');
      const fp = document.createElement('div'); fp.id = 'free-debate-panel';
      fp.innerHTML = '<div id="free-pro-speeches">old</div>';
      document.body.appendChild(fp);
      showFreePanel();
      expect(document.getElementById('free-pro-speeches').innerHTML).toBe('');
    });

    it('showFreePanel clears previous con speeches', async () => {
      const { showFreePanel } = await import('../ui.js');
      const fp = document.createElement('div'); fp.id = 'free-debate-panel';
      fp.innerHTML = '<div id="free-con-speeches">old</div>';
      document.body.appendChild(fp);
      showFreePanel();
      expect(document.getElementById('free-con-speeches').innerHTML).toBe('');
    });
  });

  describe('appendFreeSpeechToken', () => {
    it('appends tokens to persistent side-level text box', async () => {
      const { appendFreeSpeechToken, showFreePanel } = await import('../ui.js');
      const fp = document.createElement('div'); fp.id = 'free-debate-panel';
      fp.innerHTML = '<div id="free-pro-speeches"></div><div id="free-con-speeches"></div>';
      document.body.appendChild(fp);
      showFreePanel();

      appendFreeSpeechToken('pro', '第一', 1);
      appendFreeSpeechToken('pro', '句', 1);

      const proSpeeches = document.getElementById('free-pro-speeches');
      expect(proSpeeches.children.length).toBe(1);
      expect(proSpeeches.querySelector('.free-speech').textContent).toBe('第一句');
    });

    it('con and pro have separate text boxes', async () => {
      const { appendFreeSpeechToken, showFreePanel } = await import('../ui.js');
      const fp = document.createElement('div'); fp.id = 'free-debate-panel';
      fp.innerHTML = '<div id="free-pro-speeches"></div><div id="free-con-speeches"></div>';
      document.body.appendChild(fp);
      showFreePanel();

      appendFreeSpeechToken('pro', 'pro content', 1);
      appendFreeSpeechToken('con', 'con content', 1);

      expect(document.getElementById('free-pro-speeches').querySelector('.free-speech').textContent).toBe('pro content');
      expect(document.getElementById('free-con-speeches').querySelector('.free-speech').textContent).toBe('con content');
    });
  });

  describe('resetFreeSpeechEntry', () => {
    it('resets so same side creates a new entry after reset', async () => {
      const { appendFreeSpeechToken, showFreePanel, resetFreeSpeechEntry } = await import('../ui.js');
      const fp = document.createElement('div'); fp.id = 'free-debate-panel';
      fp.innerHTML = '<div id="free-pro-speeches"></div><div id="free-con-speeches"></div>';
      document.body.appendChild(fp);
      showFreePanel();

      appendFreeSpeechToken('pro', 'first', 1);
      resetFreeSpeechEntry();
      appendFreeSpeechToken('pro', 'second', 2);

      const proSpeeches = document.getElementById('free-pro-speeches');
      expect(proSpeeches.children.length).toBe(2);
    });
  });
});

// ── Free debate role-box-only SSE routing ──

describe('free debate SSE routing (role-box-only)', () => {
  beforeEach(async () => {
    document.body.innerHTML = '';
    buildModuleLayout();
    buildAncillaryDOM();
    const { setInFreeDebate, setFreeDebateRound, setFreeCurrentSpeaker } = await import('../debate.js');
    setInFreeDebate(false);
    setFreeDebateRound(0);
    setFreeCurrentSpeaker('');
  });

  it('phase_start for free_debate sets inFreeDebate=true, highlights free debate module', async () => {
    const { handleSSEMessage, getInFreeDebate } = await import('../debate.js');

    handleSSEMessage({
      type: 'phase_start', phase: 'free_debate',
      debater: 'pro_1', role_id: 'pro_1:free_debate', round_num: 1,
    });

    expect(getInFreeDebate()).toBe(true);
    expect(document.getElementById('module-free-debate').classList.contains('active-module')).toBe(true);
  });

  it('free debate panel never gets visible class', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage({
      type: 'phase_start', phase: 'free_debate',
      debater: 'pro_1', role_id: 'pro_1:free_debate', round_num: 1,
    });

    const panel = document.getElementById('free-debate-panel');
    expect(panel.classList.contains('visible')).toBe(false);
  });

  it('speech_chunk during free debate routes to role box, NOT bottom panel', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage({
      type: 'phase_start', phase: 'free_debate',
      debater: 'pro_1', role_id: 'pro_1:free_debate', round_num: 1,
    });

    handleSSEMessage({
      type: 'speech_chunk', debater: 'pro_1',
      phase: 'free_debate', role_id: 'pro_1:free_debate',
      content: '自由辩论发言',
    });
    await new Promise(r => setTimeout(r, 50));

    // Role box gets content
    expect(document.getElementById('speech-pro_1:free_debate').textContent).toContain('自由辩论发言');

    // Bottom panel stays empty
    expect(document.getElementById('free-pro-speeches').innerHTML).toBe('');
  });

  it('speech_chunk during free debate accumulates in role box via typewriter', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage({
      type: 'phase_start', phase: 'free_debate',
      debater: 'pro_1', role_id: 'pro_1:free_debate', round_num: 1,
    });

    handleSSEMessage({
      type: 'speech_chunk', debater: 'pro_1',
      phase: 'free_debate', role_id: 'pro_1:free_debate', content: '第一句',
    });
    handleSSEMessage({
      type: 'speech_chunk', debater: 'pro_1',
      phase: 'free_debate', role_id: 'pro_1:free_debate', content: '第二句',
    });
    await new Promise(r => setTimeout(r, 50));

    expect(document.getElementById('speech-pro_1:free_debate').textContent).toContain('第一句');
    expect(document.getElementById('speech-pro_1:free_debate').textContent).toContain('第二句');
  });

  it('DIFFERENT pro debaters write to DIFFERENT role boxes without overwriting', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage({
      type: 'phase_start', phase: 'free_debate',
      debater: 'pro_1', role_id: 'pro_1:free_debate', round_num: 1,
    });
    handleSSEMessage({
      type: 'speech_chunk', debater: 'pro_1',
      phase: 'free_debate', role_id: 'pro_1:free_debate', content: 'pro1发言',
    });
    await new Promise(r => setTimeout(r, 50));
    handleSSEMessage({ type: 'phase_end', phase: 'free_debate' });

    handleSSEMessage({
      type: 'phase_start', phase: 'free_debate',
      debater: 'con_1', role_id: 'con_1:free_debate', round_num: 2,
    });
    handleSSEMessage({
      type: 'speech_chunk', debater: 'con_1',
      phase: 'free_debate', role_id: 'con_1:free_debate', content: 'con1发言',
    });
    await new Promise(r => setTimeout(r, 50));
    handleSSEMessage({ type: 'phase_end', phase: 'free_debate' });

    handleSSEMessage({
      type: 'phase_start', phase: 'free_debate',
      debater: 'pro_2', role_id: 'pro_2:free_debate', round_num: 3,
    });
    handleSSEMessage({
      type: 'speech_chunk', debater: 'pro_2',
      phase: 'free_debate', role_id: 'pro_2:free_debate', content: 'pro2发言',
    });
    await new Promise(r => setTimeout(r, 50));

    // Each debater has own role box
    expect(document.getElementById('speech-pro_1:free_debate').textContent).toContain('pro1发言');
    expect(document.getElementById('speech-con_1:free_debate').textContent).toContain('con1发言');
    expect(document.getElementById('speech-pro_2:free_debate').textContent).toContain('pro2发言');
    // pro_1 content preserved
    expect(document.getElementById('speech-pro_1:free_debate').textContent).toBe('pro1发言');
  });

  it('speech_chunk OUTSIDE free debate routes to role box correctly', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage({
      type: 'phase_start', phase: 'pro_opening',
      debater: 'pro_1', role_id: 'pro_1:pro_opening', round_num: 1,
    });

    handleSSEMessage({
      type: 'speech_chunk', debater: 'pro_1',
      phase: 'pro_opening', role_id: 'pro_1:pro_opening', content: 'opening',
    });
    await new Promise(r => setTimeout(r, 50));

    expect(document.getElementById('speech-pro_1:pro_opening').textContent).toContain('opening');
  });

  it('phase_end for free_debate sets active role to done', async () => {
    const { handleSSEMessage, getInFreeDebate } = await import('../debate.js');

    handleSSEMessage({
      type: 'phase_start', phase: 'free_debate',
      debater: 'pro_1', role_id: 'pro_1:free_debate', round_num: 1,
    });
    handleSSEMessage({ type: 'phase_end', phase: 'free_debate' });

    expect(getInFreeDebate()).toBe(true);
    const badge = document.getElementById('status-pro_1:free_debate');
    expect(badge.textContent).toBe('已完成');
    expect(badge.classList.contains('done')).toBe(true);
  });

  it('debate_end marks all debaters done and exits free debate mode', async () => {
    const { handleSSEMessage, getInFreeDebate } = await import('../debate.js');

    handleSSEMessage({ type: 'phase_start', phase: 'free_debate',
      debater: 'pro_1', role_id: 'pro_1:free_debate', round_num: 1 });
    handleSSEMessage({ type: 'speech_chunk', debater: 'pro_1',
      phase: 'free_debate', role_id: 'pro_1:free_debate', content: 'content' });

    handleSSEMessage({ type: 'debate_end', debate_id: 'test', verdict: null });

    expect(getInFreeDebate()).toBe(false);
    // All free debate role boxes should have done status
    const freeIds = ALL_ROLE_IDS.filter(id => id.endsWith(':free_debate'));
    freeIds.forEach(roleId => {
      const badge = document.getElementById('status-' + roleId);
      expect(badge.classList.contains('done'), `status-${roleId} should be done`).toBe(true);
    });
  });
});

// ── Full free debate exchange simulation ──

describe('full free debate exchange simulation (role-box-only)', () => {
  beforeEach(async () => {
    document.body.innerHTML = '';
    buildModuleLayout();
    buildAncillaryDOM();
    const { setInFreeDebate, setFreeDebateRound, setFreeCurrentSpeaker } = await import('../debate.js');
    setInFreeDebate(false);
    setFreeDebateRound(0);
    setFreeCurrentSpeaker('');
  });

  it('3 exchanges (6 speakers): each role box gets correct content', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    // Exchange 1: pro_1
    handleSSEMessage({ type: 'phase_start', phase: 'free_debate',
      debater: 'pro_1', role_id: 'pro_1:free_debate', round_num: 1 });
    handleSSEMessage({ type: 'speech_chunk', debater: 'pro_1',
      phase: 'free_debate', role_id: 'pro_1:free_debate', content: '正方第一' });
    handleSSEMessage({ type: 'speech_chunk', debater: 'pro_1',
      phase: 'free_debate', role_id: 'pro_1:free_debate', content: '次发言' });
    await new Promise(r => setTimeout(r, 50));
    handleSSEMessage({ type: 'phase_end', phase: 'free_debate' });

    // Exchange 1: con_1
    handleSSEMessage({ type: 'phase_start', phase: 'free_debate',
      debater: 'con_1', role_id: 'con_1:free_debate', round_num: 1 });
    handleSSEMessage({ type: 'speech_chunk', debater: 'con_1',
      phase: 'free_debate', role_id: 'con_1:free_debate', content: '反方回应' });
    await new Promise(r => setTimeout(r, 50));
    handleSSEMessage({ type: 'phase_end', phase: 'free_debate' });

    // Exchange 2: pro_2
    handleSSEMessage({ type: 'phase_start', phase: 'free_debate',
      debater: 'pro_2', role_id: 'pro_2:free_debate', round_num: 1 });
    handleSSEMessage({ type: 'speech_chunk', debater: 'pro_2',
      phase: 'free_debate', role_id: 'pro_2:free_debate', content: '继续反驳' });
    await new Promise(r => setTimeout(r, 50));
    handleSSEMessage({ type: 'phase_end', phase: 'free_debate' });

    // Exchange 2: con_2
    handleSSEMessage({ type: 'phase_start', phase: 'free_debate',
      debater: 'con_2', role_id: 'con_2:free_debate', round_num: 1 });
    handleSSEMessage({ type: 'speech_chunk', debater: 'con_2',
      phase: 'free_debate', role_id: 'con_2:free_debate', content: '反方再驳' });
    await new Promise(r => setTimeout(r, 50));
    handleSSEMessage({ type: 'phase_end', phase: 'free_debate' });

    // Exchange 3: pro_3
    handleSSEMessage({ type: 'phase_start', phase: 'free_debate',
      debater: 'pro_3', role_id: 'pro_3:free_debate', round_num: 1 });
    handleSSEMessage({ type: 'speech_chunk', debater: 'pro_3',
      phase: 'free_debate', role_id: 'pro_3:free_debate', content: '最后补充' });
    await new Promise(r => setTimeout(r, 50));
    handleSSEMessage({ type: 'phase_end', phase: 'free_debate' });

    // Exchange 3: con_3
    handleSSEMessage({ type: 'phase_start', phase: 'free_debate',
      debater: 'con_3', role_id: 'con_3:free_debate', round_num: 1 });
    handleSSEMessage({ type: 'speech_chunk', debater: 'con_3',
      phase: 'free_debate', role_id: 'con_3:free_debate', content: '反方终结' });
    await new Promise(r => setTimeout(r, 50));
    handleSSEMessage({ type: 'phase_end', phase: 'free_debate' });

    // Verify: each role box has its own content, NOT shared
    expect(document.getElementById('speech-pro_1:free_debate').textContent).toContain('正方第一次发言');
    expect(document.getElementById('speech-con_1:free_debate').textContent).toContain('反方回应');
    expect(document.getElementById('speech-pro_2:free_debate').textContent).toContain('继续反驳');
    expect(document.getElementById('speech-con_2:free_debate').textContent).toContain('反方再驳');
    expect(document.getElementById('speech-pro_3:free_debate').textContent).toContain('最后补充');
    expect(document.getElementById('speech-con_3:free_debate').textContent).toContain('反方终结');

    // Bottom panel stays empty throughout
    expect(document.getElementById('free-pro-speeches').innerHTML).toBe('');
    expect(document.getElementById('free-con-speeches').innerHTML).toBe('');
  });

  it('pro_1 content preserved after pro_2 speaks (separate boxes)', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage({ type: 'phase_start', phase: 'free_debate',
      debater: 'pro_1', role_id: 'pro_1:free_debate', round_num: 1 });
    handleSSEMessage({ type: 'speech_chunk', debater: 'pro_1',
      phase: 'free_debate', role_id: 'pro_1:free_debate', content: 'pro_1内容' });
    await new Promise(r => setTimeout(r, 50));
    handleSSEMessage({ type: 'phase_end', phase: 'free_debate' });

    handleSSEMessage({ type: 'phase_start', phase: 'free_debate',
      debater: 'con_1', role_id: 'con_1:free_debate', round_num: 2 });
    handleSSEMessage({ type: 'speech_chunk', debater: 'con_1',
      phase: 'free_debate', role_id: 'con_1:free_debate', content: 'con_1内容' });
    await new Promise(r => setTimeout(r, 50));
    handleSSEMessage({ type: 'phase_end', phase: 'free_debate' });

    handleSSEMessage({ type: 'phase_start', phase: 'free_debate',
      debater: 'pro_2', role_id: 'pro_2:free_debate', round_num: 3 });
    handleSSEMessage({ type: 'speech_chunk', debater: 'pro_2',
      phase: 'free_debate', role_id: 'pro_2:free_debate', content: 'pro_2内容' });
    await new Promise(r => setTimeout(r, 50));

    // pro_1 box still has its content
    expect(document.getElementById('speech-pro_1:free_debate').textContent).toContain('pro_1内容');
    // pro_2 box has its own content
    expect(document.getElementById('speech-pro_2:free_debate').textContent).toContain('pro_2内容');
  });
});

// ── History replay during free debate ──

describe('history_replay during free_debate (reconnection)', () => {
  beforeEach(async () => {
    document.body.innerHTML = '';
    buildModuleLayout();
    buildAncillaryDOM();
    const { setInFreeDebate } = await import('../debate.js');
    setInFreeDebate(false);
  });

  it('sets inFreeDebate=true on reconnect during free_debate', async () => {
    const { handleSSEMessage, getInFreeDebate } = await import('../debate.js');

    expect(getInFreeDebate()).toBe(false);

    handleSSEMessage({
      type: 'history_replay',
      debate_id: 'deb-test',
      current_round: 1, total_rounds: 1,
      current_phase: 'free_debate',
      paused: false, status: 'active',
      speeches: [
        { debater: 'pro_1', phase: 'free_debate', round_num: 1,
          content: 'pro1 content', thinking: '', seq: 1, speech_type: 'free_debate' },
        { debater: 'con_1', phase: 'free_debate', round_num: 1,
          content: 'con1 content', thinking: '', seq: 2, speech_type: 'free_debate' },
      ],
      debater_status: {},
    });

    expect(getInFreeDebate()).toBe(true);
  });

  it('restores free debate speeches to individual role boxes', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage({
      type: 'history_replay',
      debate_id: 'deb-test',
      current_round: 1, total_rounds: 1,
      current_phase: 'free_debate',
      paused: false, status: 'active',
      speeches: [
        { debater: 'pro_1', phase: 'free_debate', round_num: 1,
          content: '正方第一段发言', thinking: '', seq: 1, speech_type: 'free_debate' },
        { debater: 'con_1', phase: 'free_debate', round_num: 1,
          content: '反方第一段发言', thinking: '', seq: 2, speech_type: 'free_debate' },
        { debater: 'pro_2', phase: 'free_debate', round_num: 1,
          content: '正方第二段发言', thinking: '', seq: 3, speech_type: 'free_debate' },
      ],
      debater_status: {},
    });

    // Each speech goes to its own role box
    expect(document.getElementById('speech-pro_1:free_debate').textContent).toContain('正方第一段发言');
    expect(document.getElementById('speech-con_1:free_debate').textContent).toContain('反方第一段发言');
    expect(document.getElementById('speech-pro_2:free_debate').textContent).toContain('正方第二段发言');

    // Bottom panel stays empty
    expect(document.getElementById('free-pro-speeches').innerHTML).toBe('');
  });

  it('non-free-debate speeches are NOT restored to free debate role boxes', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage({
      type: 'history_replay',
      debate_id: 'deb-test',
      current_round: 1, total_rounds: 1,
      current_phase: 'free_debate',
      paused: false, status: 'active',
      speeches: [
        { debater: 'pro_1', phase: 'pro_opening', round_num: 1,
          content: 'opening speech', thinking: '', seq: 1, speech_type: 'opening' },
        { debater: 'pro_2', phase: 'free_debate', round_num: 1,
          content: 'free debate speech', thinking: '', seq: 2, speech_type: 'free_debate' },
      ],
      debater_status: {},
    });

    // pro_1:free_debate box should NOT have opening speech
    expect(document.getElementById('speech-pro_1:free_debate').textContent).not.toContain('opening speech');
    // pro_2:free_debate box should have free debate speech
    expect(document.getElementById('speech-pro_2:free_debate').textContent).toContain('free debate speech');
  });
});

// ── Cross-examination: no bottom panel ──

describe('cross-examination role-box-only rendering', () => {
  beforeEach(async () => {
    document.body.innerHTML = '';
    buildModuleLayout();
    buildAncillaryDOM();
    const { setInFreeDebate, setFreeDebateRound, setFreeCurrentSpeaker } = await import('../debate.js');
    setInFreeDebate(false);
    setFreeDebateRound(0);
    setFreeCurrentSpeaker('');
  });

  it('cross-examination panel never gets visible class', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage({
      type: 'phase_start', phase: 'pro_cross_examine',
      debater: 'pro_3', role_id: 'pro_3:pro_cross_examine', round_num: 1,
    });

    const panel = document.getElementById('cross-examine-panel');
    expect(panel.classList.contains('visible')).toBe(false);
  });

  it('cross_q_chunk and cross_a_chunk do NOT leak into free debate panel', async () => {
    const { handleSSEMessage } = await import('../debate.js');

    handleSSEMessage({
      type: 'phase_start', phase: 'pro_cross_examine',
      debater: 'pro_3', role_id: 'pro_3:pro_cross_examine', round_num: 1,
    });
    handleSSEMessage({ type: 'cross_q_chunk', content: 'cross Q?', round: 1, examiner: 'pro_3' });
    handleSSEMessage({ type: 'cross_a_chunk', content: 'cross A.', round: 1, responder: 'con_2' });
    handleSSEMessage({ type: 'phase_end', phase: 'pro_cross_examine' });

    // Free debate panel should be empty
    expect(document.getElementById('free-pro-speeches').textContent).not.toContain('cross Q');
    expect(document.getElementById('free-pro-speeches').textContent).not.toContain('cross A');
  });
});
