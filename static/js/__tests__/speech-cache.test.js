// ── Speech Cache Tests ──
// Tests for getCachedSpeeches, setCachedSpeeches, clearCachedSpeeches
// and enterDebate cache-first behavior.

import { describe, it, expect, beforeEach } from 'vitest';

// Import from debate.js — functions that manage the speechCache Map.
// We import the real module BUT mock fetch for enterDebate tests.
import {
  getCachedSpeeches,
  setCachedSpeeches,
  clearCachedSpeeches,
} from '../debate.js';

describe('SpeechCache', () => {
  beforeEach(() => {
    // Clear cache between tests by deleting all known keys
    // (there's no public clearAll, so we clear per-debate)
    clearCachedSpeeches('test-1');
    clearCachedSpeeches('test-2');
    clearCachedSpeeches('nonexistent');
    // Also clear any entries created by side-effect
    ['d1', 'd2', 'debate-1'].forEach(id => clearCachedSpeeches(id));
  });

  it('getCachedSpeeches returns null for unknown id', () => {
    expect(getCachedSpeeches('nonexistent')).toBeNull();
  });

  it('setCachedSpeeches stores data and getCachedSpeeches retrieves it', () => {
    const data = { speeches: [{ debater: 'pro_1', content: 'Hi' }], total_rounds: 1 };
    setCachedSpeeches('test-1', data);
    const result = getCachedSpeeches('test-1');
    expect(result).not.toBeNull();
    expect(result.speeches).toHaveLength(1);
    expect(result.speeches[0].content).toBe('Hi');
    expect(result.total_rounds).toBe(1);
  });

  it('clearCachedSpeeches removes entry', () => {
    setCachedSpeeches('test-2', { speeches: [], total_rounds: 1 });
    expect(getCachedSpeeches('test-2')).not.toBeNull();
    clearCachedSpeeches('test-2');
    expect(getCachedSpeeches('test-2')).toBeNull();
  });

  it('clearCachedSpeeches on nonexistent id does not throw', () => {
    expect(() => clearCachedSpeeches('nonexistent')).not.toThrow();
  });

  it('setCachedSpeeches overwrites existing entry', () => {
    setCachedSpeeches('test-1', { speeches: [{ content: 'old' }], total_rounds: 1 });
    setCachedSpeeches('test-1', { speeches: [{ content: 'new' }], total_rounds: 2 });
    const result = getCachedSpeeches('test-1');
    expect(result.speeches[0].content).toBe('new');
    expect(result.total_rounds).toBe(2);
  });

  it('multiple independent entries do not interfere', () => {
    setCachedSpeeches('d1', { speeches: [{ content: 'one' }], total_rounds: 1 });
    setCachedSpeeches('d2', { speeches: [{ content: 'two' }], total_rounds: 2 });
    expect(getCachedSpeeches('d1').speeches[0].content).toBe('one');
    expect(getCachedSpeeches('d2').speeches[0].content).toBe('two');
    clearCachedSpeeches('d1');
    expect(getCachedSpeeches('d1')).toBeNull();
    expect(getCachedSpeeches('d2')).not.toBeNull();
  });

  it('getCachedSpeeches returns same object reference', () => {
    const data = { speeches: [], total_rounds: 1 };
    setCachedSpeeches('debate-1', data);
    const result = getCachedSpeeches('debate-1');
    expect(result).toBe(data); // Same reference
  });
});
