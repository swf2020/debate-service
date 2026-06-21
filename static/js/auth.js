// ── Auth Module ──
// Token management, login/register, user state

let currentUser = null;
let authCallbacks = [];

export function getToken() {
  return localStorage.getItem('debate_token');
}

function setToken(token) {
  localStorage.setItem('debate_token', token);
}

function clearToken() {
  localStorage.removeItem('debate_token');
}

export function getUser() {
  return currentUser;
}

export function isAdmin() {
  return currentUser && currentUser.is_admin;
}

export function onAuthChange(fn) {
  authCallbacks.push(fn);
}

function notifyAuthChange(event) {
  authCallbacks.forEach(fn => fn(event));
}

export function authHeaders() {
  const token = getToken();
  const h = { 'Content-Type': 'application/json' };
  if (token) h['Authorization'] = 'Bearer ' + token;
  return h;
}

// ── UI helpers ──

function showAuthOverlay() {
  document.getElementById('auth-panel').classList.remove('hidden');
  document.getElementById('user-bar').classList.add('hidden');
  document.getElementById('main-content').classList.add('hidden');
}

function showAppShell() {
  document.getElementById('auth-panel').classList.add('hidden');
  document.getElementById('user-bar').classList.remove('hidden');
  document.getElementById('main-content').classList.remove('hidden');
}

// ── API calls ──

export async function handleLogin(e) {
  e.preventDefault();
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;
  const errEl = document.getElementById('login-error');
  errEl.textContent = '';

  try {
    const resp = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      errEl.textContent = data.detail || '登录失败';
      return;
    }
    setToken(data.token);
    currentUser = data.user;
    showAppShell();
    updateUserBar();
    notifyAuthChange({ type: 'login', user: data.user });
  } catch (err) {
    errEl.textContent = '网络错误: ' + err.message;
  }
}

export async function handleRegister(e) {
  e.preventDefault();
  const username = document.getElementById('register-username').value.trim();
  const password = document.getElementById('register-password').value;
  const errEl = document.getElementById('register-error');
  const succEl = document.getElementById('register-success');
  errEl.textContent = '';
  succEl.textContent = '';

  try {
    const resp = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      errEl.textContent = data.detail || '注册失败';
      return;
    }
    succEl.textContent = '注册成功！';
    setToken(data.token);
    currentUser = data.user;
    setTimeout(() => {
      showAppShell();
      updateUserBar();
      notifyAuthChange({ type: 'login', user: data.user });
    }, 600);
  } catch (err) {
    errEl.textContent = '网络错误: ' + err.message;
  }
}

export function logout() {
  clearToken();
  currentUser = null;
  showAuthOverlay();
  notifyAuthChange({ type: 'logout' });
}

export async function checkAuth() {
  const token = getToken();
  if (!token) {
    showAuthOverlay();
    return false;
  }

  try {
    const resp = await fetch('/api/auth/me', {
      headers: { 'Authorization': 'Bearer ' + token },
    });
    if (!resp.ok) {
      clearToken();
      showAuthOverlay();
      return false;
    }
    const data = await resp.json();
    currentUser = data.user;
    showAppShell();
    updateUserBar();
    notifyAuthChange({ type: 'login', user: data.user });
    return true;
  } catch (err) {
    showAuthOverlay();
    return false;
  }
}

export function updateUserBar() {
  const user = currentUser;
  if (!user) return;
  document.getElementById('current-username').textContent = user.username;

  const adminLink = document.getElementById('admin-link');
  if (user.is_admin) {
    adminLink.classList.remove('hidden');
  } else {
    adminLink.classList.add('hidden');
  }
}
