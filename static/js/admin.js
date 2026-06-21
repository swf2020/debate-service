// ── Admin Module ──
// Admin modal: user list with expandable debate rows

import { getToken } from './auth.js';
import { hideModal, escapeHtml } from './ui.js';

let adminExpandedUsers = {};

function adminAuthHeaders() {
  const token = getToken();
  const h = {};
  if (token) h['Authorization'] = 'Bearer ' + token;
  return h;
}

export async function showAdminPanel() {
  document.getElementById('admin-modal').style.display = 'flex';
  const contentEl = document.getElementById('admin-content');
  contentEl.innerHTML = '<div style="text-align:center;color:var(--color-text-dim);padding:var(--space-8);">加载中...</div>';

  const token = getToken();
  if (!token) {
    contentEl.innerHTML = '<div style="text-align:center;color:var(--color-error);padding:var(--space-8);">请先登录</div>';
    return;
  }

  try {
    const resp = await fetch('/api/admin/users', { headers: adminAuthHeaders() });
    if (resp.status === 401 || resp.status === 403) {
      contentEl.innerHTML = '<div style="text-align:center;color:var(--color-error);padding:var(--space-8);">无权访问，请使用管理员账号登录</div>';
      return;
    }
    const data = await resp.json();
    renderAdminUsers(data.users || []);
  } catch (err) {
    contentEl.innerHTML = '<div style="text-align:center;color:var(--color-error);padding:var(--space-8);">加载失败: ' + err.message + '</div>';
  }
}

function renderAdminUsers(users) {
  const contentEl = document.getElementById('admin-content');
  let html = '<table class="admin-table"><thead><tr><th>用户名</th><th>角色</th><th>辩论数</th><th>注册时间</th></tr></thead><tbody>';

  users.forEach(u => {
    html += '<tr class="user-row" data-user-id="' + u.id + '">';
    html += '<td>' + escapeHtml(u.username) + '</td>';
    html += '<td>' + (u.is_admin ? '管理员' : '用户') + '</td>';
    html += '<td>' + u.debate_count + '</td>';
    html += '<td>' + (u.created_at ? u.created_at.slice(0, 10) : '-') + '</td>';
    html += '</tr>';
    html += '<tr class="debate-row" id="debates-' + u.id + '" style="display:none"><td colspan="4"><div class="debate-list" id="debate-list-' + u.id + '"></div></td></tr>';
  });

  html += '</tbody></table>';
  contentEl.innerHTML = html;

  // Bind user row clicks
  contentEl.querySelectorAll('.user-row').forEach(row => {
    row.addEventListener('click', () => toggleUserDebates(row, row.dataset.userId));
  });
}

async function toggleUserDebates(row, userId) {
  const debateRow = document.getElementById('debates-' + userId);
  if (debateRow.style.display !== 'none') {
    debateRow.style.display = 'none';
    row.classList.remove('expanded');
    return;
  }

  debateRow.style.display = '';
  row.classList.add('expanded');

  const listEl = document.getElementById('debate-list-' + userId);
  if (listEl.children.length > 0) return;

  listEl.innerHTML = '<div style="color:var(--color-text-dim);padding:var(--space-2);text-align:center;">加载中...</div>';

  try {
    const resp = await fetch('/api/admin/users/' + userId + '/debates', { headers: adminAuthHeaders() });
    const data = await resp.json();

    if (!data.debates.length) {
      listEl.innerHTML = '<div style="color:var(--color-text-muted);padding:var(--space-2);text-align:center;">暂无辩论</div>';
      return;
    }

    let html = '';
    data.debates.forEach(d => {
      const statusClass = d.status === 'running' ? 'status-running' : d.status === 'paused' ? 'status-paused' : 'status-finished';
      const statusLabel = d.status === 'running' ? '进行中' : d.status === 'paused' ? '已暂停' : '已完成';
      html += '<div class="debate-item-admin">';
      html += '<span style="font-weight:600;">' + escapeHtml(d.topic) + '</span>';
      html += '<span style="font-size:0.72rem;color:var(--color-text-muted);"><span class="history-status ' + d.status + '">' + statusLabel + '</span>';
      html += ' ' + d.total_rounds + '轮 | 胜方: ' + (d.winner || '-') + ' | ' + (d.created_at ? d.created_at.slice(0, 10) : '-') + '</span>';
      html += '</div>';
    });
    listEl.innerHTML = html;
  } catch (err) {
    listEl.innerHTML = '<div style="color:var(--color-error);padding:var(--space-2);">加载失败</div>';
  }
}

export function hideAdminPanel() {
  hideModal('admin-modal');
}
