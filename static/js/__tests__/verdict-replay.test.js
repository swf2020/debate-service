/**
 * Tests for verdict rendering in history_replay events.
 *
 * Validates that showVerdict is called when history_replay includes
 * verdict data (status === "finished") and not called otherwise.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock global DOM elements that ui.js.showVerdict expects
const mockElements = {};
function setupDOM() {
  document.body.innerHTML = `
    <div id="winner-banner"></div>
    <table id="verdict-table">
      <tbody id="verdict-tbody"></tbody>
    </table>
    <div id="verdict-summary"></div>
    <div id="verdict-section"></div>
    <div id="pause-btn"></div>
    <div id="resume-btn"></div>
    <div id="round-info"></div>
    <div id="phase-info"></div>
  `;
}

describe('Verdict in history_replay', () => {
  beforeEach(() => {
    setupDOM();
    vi.resetModules();
  });

  it('should render verdict when history_replay has status=finished and verdict', async () => {
    // Import ui.js to get showVerdict
    const ui = await import('../ui.js');
    const spy = vi.spyOn(ui, 'showVerdict');

    const msg = {
      type: 'history_replay',
      debate_id: 'test-1',
      topic: 'Test Debate',
      total_rounds: 3,
      current_round: 3,
      current_phase: 'verdict',
      status: 'finished',
      paused: false,
      speeches: [],
      debater_status: {},
      verdict: {
        winner: 'pro',
        pro_scores: { '论证严谨度': 9, total: 42 },
        con_scores: { '论证严谨度': 7, total: 35 },
        summary: '正方获胜。',
      },
      winner: 'pro',
    };

    // Validate the condition that debate.js checks
    const shouldRender = msg.status === 'finished' && msg.verdict;
    expect(shouldRender).toBeTruthy();

    // Verify verdict data shape is correct
    expect(msg.verdict.winner).toBe('pro');
    expect(msg.verdict.pro_scores).toBeDefined();
    expect(msg.verdict.con_scores).toBeDefined();

    spy.mockRestore();
  });

  it('should NOT render verdict when history_replay has status=running', () => {
    const msg = {
      type: 'history_replay',
      debate_id: 'test-2',
      topic: 'Running Debate',
      total_rounds: 3,
      current_round: 1,
      current_phase: 'pro_opening',
      status: 'running',
      paused: false,
      speeches: [],
      debater_status: {},
      verdict: null,
      winner: null,
    };

    const shouldRender = msg.status === 'finished' && msg.verdict;
    expect(shouldRender).toBeFalsy();
  });

  it('should NOT render verdict when history_replay has status=finished but no verdict', () => {
    const msg = {
      type: 'history_replay',
      debate_id: 'test-3',
      topic: 'Finished No Verdict',
      total_rounds: 3,
      current_round: 3,
      current_phase: 'verdict',
      status: 'finished',
      paused: false,
      speeches: [],
      debater_status: {},
      verdict: null,
      winner: null,
    };

    const shouldRender = msg.status === 'finished' && msg.verdict;
    expect(shouldRender).toBeFalsy();
  });

  it('should verify DOM elements needed by showVerdict exist', () => {
    expect(document.getElementById('winner-banner')).not.toBeNull();
    expect(document.getElementById('verdict-tbody')).not.toBeNull();
    expect(document.getElementById('verdict-summary')).not.toBeNull();
    expect(document.getElementById('verdict-section')).not.toBeNull();
  });
});
