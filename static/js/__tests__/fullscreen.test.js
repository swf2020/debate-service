import { describe, it, expect, beforeEach, afterEach } from 'vitest';

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

describe('fullscreen toggle', () => {
  let grid;

  beforeEach(() => {
    document.body.innerHTML = '';
  });

  afterEach(() => {
    if (grid && grid.parentNode) grid.parentNode.removeChild(grid);
  });

  describe('toggleDebaterFullscreen', () => {
    it('adds "fullscreen" class to a debater cell when toggled on', async () => {
      // Dynamically import the module under test
      const { toggleDebaterFullscreen } = await import('../ui.js');
      const cell = buildDebaterCell('pro_1', 'pro-cell');
      document.body.appendChild(cell);

      toggleDebaterFullscreen(cell);
      expect(cell.classList.contains('fullscreen')).toBe(true);
    });

    it('removes "fullscreen" class from a debater cell when toggled off', async () => {
      const { toggleDebaterFullscreen } = await import('../ui.js');
      const cell = buildDebaterCell('pro_1', 'pro-cell');
      cell.classList.add('fullscreen');
      document.body.appendChild(cell);

      toggleDebaterFullscreen(cell);
      expect(cell.classList.contains('fullscreen')).toBe(false);
    });

    it('updates fullscreen button title to "还原" when fullscreen is on', async () => {
      const { toggleDebaterFullscreen } = await import('../ui.js');
      const { injectFullscreenButtons } = await import('../ui.js');
      const cell = buildDebaterCell('pro_1', 'pro-cell');
      document.body.appendChild(cell);
      injectFullscreenButtons();

      toggleDebaterFullscreen(cell);
      const btn = cell.querySelector('.fullscreen-btn');
      expect(btn.title).toBe('还原');
    });

    it('updates fullscreen button title to "全屏查看" when fullscreen is off', async () => {
      const { toggleDebaterFullscreen } = await import('../ui.js');
      const { injectFullscreenButtons } = await import('../ui.js');
      const cell = buildDebaterCell('pro_1', 'pro-cell');
      cell.classList.add('fullscreen');
      document.body.appendChild(cell);
      injectFullscreenButtons();

      toggleDebaterFullscreen(cell);
      const btn = cell.querySelector('.fullscreen-btn');
      expect(btn.title).toBe('全屏查看');
    });
  });

  describe('injectFullscreenButtons', () => {
    it('adds a fullscreen button to every debater cell header', async () => {
      const { injectFullscreenButtons } = await import('../ui.js');
      buildDebateGrid();
      injectFullscreenButtons();

      const cells = document.querySelectorAll('.debater-cell');
      expect(cells.length).toBe(6);
      cells.forEach(cell => {
        const btn = cell.querySelector('.fullscreen-btn');
        expect(btn).not.toBeNull();
        expect(btn.tagName).toBe('BUTTON');
      });
    });

    it('does not add duplicate buttons on repeated calls', async () => {
      const { injectFullscreenButtons } = await import('../ui.js');
      buildDebateGrid();
      injectFullscreenButtons();
      injectFullscreenButtons();

      const cells = document.querySelectorAll('.debater-cell');
      cells.forEach(cell => {
        expect(cell.querySelectorAll('.fullscreen-btn').length).toBe(1);
      });
    });

    it('clicking the button toggles fullscreen on the parent cell', async () => {
      const { injectFullscreenButtons } = await import('../ui.js');
      const cell = buildDebaterCell('pro_1', 'pro-cell');
      document.body.appendChild(cell);
      injectFullscreenButtons();

      const btn = cell.querySelector('.fullscreen-btn');
      btn.click();
      expect(cell.classList.contains('fullscreen')).toBe(true);

      btn.click();
      expect(cell.classList.contains('fullscreen')).toBe(false);
    });
  });

  describe('Escape key', () => {
    it('pressing Escape exits fullscreen on a fullscreen cell', async () => {
      const { injectFullscreenButtons, toggleDebaterFullscreen, initFullscreenEscapeHandler } = await import('../ui.js');

      const cell = buildDebaterCell('pro_1', 'pro-cell');
      document.body.appendChild(cell);
      injectFullscreenButtons();
      initFullscreenEscapeHandler();
      toggleDebaterFullscreen(cell);
      expect(cell.classList.contains('fullscreen')).toBe(true);

      // Simulate Escape key
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
      expect(cell.classList.contains('fullscreen')).toBe(false);
    });

    it('pressing Escape does not affect cells that are not fullscreen', async () => {
      const { injectFullscreenButtons, initFullscreenEscapeHandler } = await import('../ui.js');

      buildDebateGrid();
      injectFullscreenButtons();
      initFullscreenEscapeHandler();
      const cells = document.querySelectorAll('.debater-cell');

      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
      cells.forEach(cell => {
        expect(cell.classList.contains('fullscreen')).toBe(false);
      });
    });
  });
});
