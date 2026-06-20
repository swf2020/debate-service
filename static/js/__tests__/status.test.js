import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// ── Test helpers: build minimal DOM for a debater cell ──

function buildDebaterCell(id, proConClass) {
  const cell = document.createElement('div');
  cell.className = `debater-cell ${proConClass}`;
  cell.id = `cell-${id}`;
  cell.dataset.debater = id;

  const header = document.createElement('div');
  header.className = 'cell-header';

  const nameDiv = document.createElement('div');
  const nameEl = document.createElement('div');
  nameEl.className = 'cell-debater-name';
  nameEl.textContent = `辩手 ${id}`;
  nameDiv.appendChild(nameEl);

  const badge = document.createElement('span');
  badge.className = 'status-badge';
  badge.id = `status-${id}`;
  badge.textContent = '等待';

  header.appendChild(nameDiv);
  header.appendChild(badge);

  const content = document.createElement('div');
  content.className = 'cell-content';

  const details = document.createElement('details');
  details.id = `details-${id}`;
  const summary = document.createElement('summary');
  summary.textContent = '思考过程';
  details.appendChild(summary);
  const thinking = document.createElement('div');
  thinking.className = 'thinking-content';
  thinking.id = `thinking-${id}`;
  details.appendChild(thinking);

  const speech = document.createElement('div');
  speech.className = 'speech-content';
  speech.id = `speech-${id}`;

  content.appendChild(details);
  content.appendChild(speech);

  cell.appendChild(header);
  cell.appendChild(content);

  return cell;
}

function buildDebateGrid() {
  const grid = document.createElement('div');
  grid.id = 'debate-grid';
  const keys = ['pro_1', 'con_1', 'pro_2', 'con_2', 'pro_3', 'con_3'];
  const classes = ['pro-cell', 'con-cell', 'pro-cell', 'con-cell', 'pro-cell', 'con-cell'];

  const row1 = document.createElement('div');
  row1.className = 'grid-row';
  row1.appendChild(buildDebaterCell(keys[0], classes[0]));
  row1.appendChild(buildDebaterCell(keys[1], classes[1]));

  const row2 = document.createElement('div');
  row2.className = 'grid-row';
  row2.appendChild(buildDebaterCell(keys[2], classes[2]));
  row2.appendChild(buildDebaterCell(keys[3], classes[3]));

  const row3 = document.createElement('div');
  row3.className = 'grid-row';
  row3.appendChild(buildDebaterCell(keys[4], classes[4]));
  row3.appendChild(buildDebaterCell(keys[5], classes[5]));

  grid.appendChild(row1);
  grid.appendChild(row2);
  grid.appendChild(row3);
  document.body.appendChild(grid);
  return grid;
}

// ── Tests ──

describe('debater status management', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  describe('setBadgeStatus', () => {
    it('sets badge to "speaking" with correct text and class', async () => {
      const { setBadgeStatus } = await import('../ui.js');
      const cell = buildDebaterCell('pro_1', 'pro-cell');
      document.body.appendChild(cell);

      setBadgeStatus('pro_1', 'speaking');
      const badge = document.getElementById('status-pro_1');
      expect(badge.textContent).toBe('发言中');
      expect(badge.classList.contains('speaking')).toBe(true);
      expect(badge.classList.contains('finishing')).toBe(false);
      expect(badge.classList.contains('done')).toBe(false);
    });

    it('sets badge to "finishing" with "输出中" text (Bug 2 fix)', async () => {
      const { setBadgeStatus } = await import('../ui.js');
      const cell = buildDebaterCell('pro_1', 'pro-cell');
      document.body.appendChild(cell);

      setBadgeStatus('pro_1', 'finishing');
      const badge = document.getElementById('status-pro_1');
      // Bug 2 fix: "finishing" must show different text than "speaking"
      // to avoid confusion (both used to show "发言中")
      expect(badge.textContent).toBe('输出中');
      expect(badge.classList.contains('finishing')).toBe(true);
      expect(badge.classList.contains('speaking')).toBe(false);
    });

    it('sets badge to "done" with "已完成" text', async () => {
      const { setBadgeStatus } = await import('../ui.js');
      const cell = buildDebaterCell('pro_1', 'pro-cell');
      document.body.appendChild(cell);

      setBadgeStatus('pro_1', 'done');
      const badge = document.getElementById('status-pro_1');
      expect(badge.textContent).toBe('已完成');
      expect(badge.classList.contains('done')).toBe(true);
    });
  });

  describe('updateAllStatusBadges', () => {
    it('does NOT override a "speaking" badge (Bug 1 fix)', async () => {
      const { setBadgeStatus, updateAllStatusBadges } = await import('../ui.js');
      buildDebateGrid();

      // Set pro_1 as "speaking" (typewriter running, speech in progress)
      setBadgeStatus('pro_1', 'speaking');

      // Backend sends state_snapshot with pro_1="done" (race condition)
      updateAllStatusBadges({ pro_1: 'done', con_1: 'waiting', pro_2: 'waiting', con_2: 'waiting', pro_3: 'waiting', con_3: 'waiting' });

      // Bug 1 fix: "speaking" badge must NOT be overwritten to "done"
      const badge = document.getElementById('status-pro_1');
      expect(badge.textContent).toBe('发言中');
      expect(badge.classList.contains('speaking')).toBe(true);
      expect(badge.classList.contains('done')).toBe(false);
    });

    it('does NOT override a "finishing" badge', async () => {
      const { setBadgeStatus, updateAllStatusBadges } = await import('../ui.js');
      buildDebateGrid();

      // Set pro_1 as "finishing" (typewriter still rendering)
      setBadgeStatus('pro_1', 'finishing');

      // Backend sends state_snapshot with pro_1="done"
      updateAllStatusBadges({ pro_1: 'done', con_1: 'waiting', pro_2: 'waiting', con_2: 'waiting', pro_3: 'waiting', con_3: 'waiting' });

      const badge = document.getElementById('status-pro_1');
      expect(badge.textContent).toBe('输出中');
      expect(badge.classList.contains('finishing')).toBe(true);
    });

    it('updates "done" badge when state says "done"', async () => {
      const { setBadgeStatus, updateAllStatusBadges } = await import('../ui.js');
      buildDebateGrid();

      setBadgeStatus('pro_1', 'done');

      // Update with different state — should still respect "done"
      updateAllStatusBadges({ pro_1: 'waiting', con_1: 'waiting', pro_2: 'waiting', con_2: 'waiting', pro_3: 'waiting', con_3: 'waiting' });

      const badge = document.getElementById('status-pro_1');
      expect(badge.textContent).toBe('等待');
    });

    it('only one badge shows "发言中" at a time (Bug 2 fix)', async () => {
      const { setBadgeStatus, updateAllStatusBadges } = await import('../ui.js');
      buildDebateGrid();

      // Simulate: pro_1 finished speaking, set to "finishing", con_1 now "speaking"
      setBadgeStatus('pro_1', 'finishing');
      setBadgeStatus('con_1', 'speaking');

      // Backend sends state_snapshot for new phase
      updateAllStatusBadges({ pro_1: 'done', con_1: 'speaking', pro_2: 'waiting', con_2: 'waiting', pro_3: 'waiting', con_3: 'waiting' });

      const pro1Badge = document.getElementById('status-pro_1');
      const con1Badge = document.getElementById('status-con_1');

      // pro_1 stays "finishing"/"输出中" (different from "发言中")
      expect(pro1Badge.classList.contains('finishing')).toBe(true);
      // con_1 stays "speaking"
      expect(con1Badge.classList.contains('speaking')).toBe(true);

      // Key assertion: the TEXT should be different
      // "finishing" → "输出中", "speaking" → "发言中"
      // This prevents the appearance of two debaters "speaking" simultaneously
      const speakingBadges = document.querySelectorAll('.status-badge.speaking');
      expect(speakingBadges.length).toBe(1); // Only con_1 is "speaking"
    });
  });
});
