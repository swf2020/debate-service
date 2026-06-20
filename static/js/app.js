// ── App Entry Point ──
// Initialization, event binding, view routing

import { checkAuth, logout, onAuthChange, handleLogin, handleRegister } from './auth.js';
import { loadHistory, showHistoryPanel, bindHistoryClicks } from './history.js';
import { startDebate, checkActiveDebate, loadSkills, pauseDebate, resumeDebate, backToList, resetToNewDebate, setBackToListCallback } from './debate.js';
import { injectFullscreenButtons, initFullscreenEscapeHandler } from './ui.js';

// Wire cross-module callback: debate.js → history.js
setBackToListCallback(loadHistory);

// ── Init ──

document.addEventListener('DOMContentLoaded', async () => {
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

  // Auth forms — bind both click (button) and submit (Enter key) handlers.
  // Forms have onsubmit="return false" as fallback against native submission.
  document.getElementById('login-submit-btn').addEventListener('click', handleLogin);
  document.getElementById('register-submit-btn').addEventListener('click', handleRegister);
  document.getElementById('login-form').addEventListener('submit', handleLogin);
  document.getElementById('register-form').addEventListener('submit', handleRegister);

  // Config toggle (optional — may not exist in minimal HTML)
  const configToggle = document.getElementById('config-toggle');
  if (configToggle) {
    configToggle.addEventListener('click', () => {
      const section = document.getElementById('config-section');
      if (section) section.classList.toggle('collapsed');
    });
  }

  // Debate controls
  document.getElementById('start-btn').addEventListener('click', startDebate);
  document.getElementById('pause-btn').addEventListener('click', pauseDebate);
  document.getElementById('resume-btn').addEventListener('click', resumeDebate);
  document.getElementById('new-debate-btn').addEventListener('click', resetToNewDebate);
  document.getElementById('back-list-btn').addEventListener('click', backToList);

  // New debate from history
  document.getElementById('new-debate-from-history')?.addEventListener('click', resetToNewDebate);
  document.getElementById('empty-start-btn')?.addEventListener('click', resetToNewDebate);

  // Logout
  document.getElementById('logout-btn').addEventListener('click', logout);

  // History "enterDebate" clicks (delegated)
  bindHistoryClicks();

  // Check auth state
  await checkAuth();

  // Inject fullscreen buttons into debater cells and bind Escape key
  injectFullscreenButtons();
  initFullscreenEscapeHandler();
});

// ── Auth change handler ──

onAuthChange(async (event) => {
  if (event.type === 'login') {
    await loadSkills();
    await loadHistory();
    await checkActiveDebate();

    // If redirected from /admin (view=admin saved in URL before checkAuth cleared it),
    // the admin modal will open via the DOMContentLoaded path above.
  }
});
