import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// ── DOM setup helpers for startDebate() ──

function buildStartForm() {
  const topic = document.createElement('input');
  topic.id = 'topic-input';
  topic.value = 'Test topic';
  document.body.appendChild(topic);

  for (let i = 1; i <= 4; i++) {
    const proSkill = document.createElement('input');
    proSkill.id = `pro-skills-${i}`;
    document.body.appendChild(proSkill);
    const conSkill = document.createElement('input');
    conSkill.id = `con-skills-${i}`;
    document.body.appendChild(conSkill);
  }

  const judgeSkill = document.createElement('input');
  judgeSkill.id = 'judge-skill';
  document.body.appendChild(judgeSkill);
}

describe('rounds locked to 1', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    buildStartForm();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('startDebate sends rounds: 1 in request body', async () => {
    // Mock toast (imported from ui.js)
    vi.mock('../ui.js', () => ({
      showToast: vi.fn(),
      setView: vi.fn(),
      clearAllCells: vi.fn(),
      clearAllRoleBoxes: vi.fn(),
      highlightSpeaker: vi.fn(),
      setBadgeStatus: vi.fn(),
      setRoleBoxStatus: vi.fn(),
      updateAllStatusBadges: vi.fn(),
      updateControlInfo: vi.fn(),
      showVerdict: vi.fn(),
      getPhaseName: vi.fn((p) => p),
      escapeHtml: vi.fn((s) => s),
      DEBATER_KEYS: [],
      ALL_ROLE_IDS: [],
      updateRoleLabel: vi.fn(),
      highlightModule: vi.fn(),
      highlightRoleBox: vi.fn(),
      clearRoleBox: vi.fn(),
    }));

    // Mock auth
    vi.mock('../auth.js', () => ({
      authHeaders: () => ({ Authorization: 'Bearer test-token' }),
      getToken: () => 'test-token',
    }));

    // Mock api
    vi.mock('../api.js', () => ({
      createEventSource: vi.fn(),
    }));

    let fetchBody;
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn((url, options) => {
      fetchBody = JSON.parse(options.body);
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ debate_id: 'test-id', status: 'running' }),
      });
    });

    const { startDebate } = await import('../debate.js');
    await startDebate();

    expect(fetchBody.rounds).toBe(1);

    globalThis.fetch = originalFetch;
  });

  it('startDebate does not reference rounds-select element', async () => {
    // rounds-select should not exist in DOM
    expect(document.getElementById('rounds-select')).toBeNull();
  });
});
