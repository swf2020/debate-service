// ── API Module ──
// Fetch wrappers with auth headers

import { authHeaders } from './auth.js';

export async function get(path) {
  const resp = await fetch(path, { headers: authHeaders() });
  return resp;
}

export async function post(path, body) {
  const resp = await fetch(path, {
    method: 'POST',
    headers: authHeaders(),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return resp;
}

export async function getJSON(path) {
  const resp = await get(path);
  return await resp.json();
}

export async function postJSON(path, body) {
  const resp = await post(path, body);
  return await resp.json();
}

export async function fetchBatchSpeeches(ids) {
  if (!ids || !ids.length) return {};
  const resp = await fetch('/api/debate/speeches/batch?ids=' + ids.join(','), {
    headers: authHeaders(),
  });
  if (!resp.ok) {
    console.error('Failed to fetch batch speeches:', resp.status);
    return {};
  }
  const data = await resp.json();
  return data.speeches || {};
}

export function createEventSource(debateId, token, onMessage, onError) {
  const es = new EventSource(
    '/api/debate/' + debateId + '/stream?token=' + encodeURIComponent(token)
  );
  es.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      onMessage(msg);
    } catch (err) {
      console.error('SSE parse error:', err);
    }
  };
  es.onerror = onError || (() => {});
  return es;
}
