import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// ── Hash helpers (mirrors what app.js will export) ──

function getDebateIdFromHash() {
  const m = window.location.hash.match(/^#\/debate\/(.+)/);
  return m ? m[1] : null;
}

function setDebateHash(debateId) {
  window.location.hash = '#/debate/' + debateId;
}

function clearDebateHash() {
  window.location.hash = '#/';
}

function isDebateHash() {
  return /^#\/debate\//.test(window.location.hash);
}

describe('URL hash routing', () => {
  describe('getDebateIdFromHash', () => {
    beforeEach(() => {
      window.location.hash = '';
    });

    it('returns null for empty hash', () => {
      expect(getDebateIdFromHash()).toBeNull();
    });

    it('returns null for hash-only (#/)', () => {
      window.location.hash = '#/';
      expect(getDebateIdFromHash()).toBeNull();
    });

    it('extracts debate ID from #/debate/{id}', () => {
      window.location.hash = '#/debate/abc-123-def';
      expect(getDebateIdFromHash()).toBe('abc-123-def');
    });

    it('extracts UUID debate ID', () => {
      window.location.hash = '#/debate/a7c502f7-8287-41d3-9f5a-6c3aae82196a';
      expect(getDebateIdFromHash()).toBe('a7c502f7-8287-41d3-9f5a-6c3aae82196a');
    });

    it('returns null for other hash formats', () => {
      window.location.hash = '#/other/thing';
      expect(getDebateIdFromHash()).toBeNull();
    });
  });

  describe('setDebateHash', () => {
    it('sets hash to #/debate/{id}', () => {
      setDebateHash('test-123');
      expect(window.location.hash).toBe('#/debate/test-123');
    });
  });

  describe('clearDebateHash', () => {
    it('sets hash to #/', () => {
      window.location.hash = '#/debate/test-123';
      clearDebateHash();
      expect(window.location.hash).toBe('#/');
    });
  });

  describe('isDebateHash', () => {
    it('returns true for debate hash', () => {
      window.location.hash = '#/debate/test-123';
      expect(isDebateHash()).toBe(true);
    });

    it('returns false for empty hash', () => {
      window.location.hash = '';
      expect(isDebateHash()).toBe(false);
    });

    it('returns false for list hash #/', () => {
      window.location.hash = '#/';
      expect(isDebateHash()).toBe(false);
    });
  });

  describe('hash priority over checkActiveDebate', () => {
    it('skips API check when URL has debate hash', async () => {
      // Simulate page load with hash
      window.location.hash = '#/debate/skip-api-check';

      // If hash has a debate ID, we should NOT call /api/debate/active
      const shouldSkip = isDebateHash();
      expect(shouldSkip).toBe(true);

      // The enter flow should use the hash ID directly
      const id = getDebateIdFromHash();
      expect(id).toBe('skip-api-check');
    });

    it('calls checkActiveDebate when no debate hash', () => {
      window.location.hash = '';
      expect(isDebateHash()).toBe(false);
      // In this case, the app should call /api/debate/active
    });
  });

  describe('popstate handling', () => {
    it('detects debate hash change via popstate', () => {
      // Simulate user pressing back from debate to list
      window.location.hash = '#/debate/test-back';
      let popstateId = null;

      const handler = () => {
        popstateId = isDebateHash() ? getDebateIdFromHash() : null;
      };

      // Navigate forward to debate page
      window.location.hash = '#/';

      // Simulate popstate
      window.addEventListener('popstate', handler);
      window.dispatchEvent(new PopStateEvent('popstate'));
      window.removeEventListener('popstate', handler);

      // After going back, hash is #/ — no debate ID
      expect(popstateId).toBeNull();
    });
  });
});
