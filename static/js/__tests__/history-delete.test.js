import { describe, it, expect, beforeAll, beforeEach, afterEach, vi } from 'vitest';

function buildHistoryDOM() {
  document.body.innerHTML = `
    <div id="history-panel">
      <div id="active-debates-section"></div>
      <div id="history-debates-section"></div>
      <div id="history-empty" class="hidden"></div>
    </div>
    <div id="config-panel"></div>
    <div id="debate-grid"></div>
    <div id="control-bar"></div>
    <div id="verdict-section"></div>
    <div id="back-list-btn"></div>
    <div id="new-debate-btn"></div>
    <div id="toast-container"></div>
  `;
}

function buildHistoryItem(id, topic) {
  return `
    <div class="history-item">
      <div class="history-item-meta">
        <div class="history-item-topic">${topic}</div>
        <div class="history-item-info">
          <span>06-21 10:00</span>
          <span>1轮</span>
          <span class="history-status finished">已完成</span>
        </div>
      </div>
      <div class="history-item-action">
        <button data-debate-id="${id}" data-debate-status="finished" class="enter-debate-btn">查看回放</button>
        <button data-debate-id="${id}" class="delete-debate-btn">删除</button>
      </div>
    </div>`;
}

describe('Delete debate from history list', () => {
  let fetchMock;

  beforeAll(async () => {
    // Bind event delegation ONCE — listener is on document, works for any DOM
    document.body.innerHTML = '<div></div>';
    const mod = await import('../history.js');
    mod.bindHistoryClicks();
  });

  beforeEach(() => {
    buildHistoryDOM();
    localStorage.setItem('debate_token', 'test-token-123');

    fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ status: 'deleted' }),
    });
    global.fetch = fetchMock;
    window.confirm = vi.fn().mockReturnValue(true);
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('removes the history-item row immediately after successful delete', async () => {
    document.getElementById('history-debates-section').innerHTML = `
      <div class="date-group expanded">
        <div class="date-items" style="max-height:none;">
          ${buildHistoryItem('debate-aaa111', '测试话题A')}
          ${buildHistoryItem('debate-bbb222', '测试话题B')}
        </div>
      </div>
    `;

    expect(document.querySelectorAll('.history-item').length).toBe(2);

    document.querySelector('[data-debate-id="debate-aaa111"].delete-debate-btn').click();
    await new Promise(r => setTimeout(r, 50));

    expect(document.querySelectorAll('.history-item').length).toBe(1);
    expect(document.querySelector('.history-item-topic').textContent).toBe('测试话题B');
  });

  it('calls DELETE /api/debate/:id with correct method and headers', async () => {
    document.getElementById('history-debates-section').innerHTML = `
      <div class="date-group expanded">
        <div class="date-items" style="max-height:none;">
          ${buildHistoryItem('debate-ccc333', '测试话题C')}
        </div>
      </div>
    `;

    document.querySelector('[data-debate-id="debate-ccc333"].delete-debate-btn').click();
    await new Promise(r => setTimeout(r, 50));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/debate/debate-ccc333');
    expect(options.method).toBe('DELETE');
    expect(options.headers['Authorization']).toBe('Bearer test-token-123');
  });

  it('does NOT remove the row on failed delete (403)', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 403,
      json: () => Promise.resolve({ detail: 'Access denied' }),
    });

    document.getElementById('history-debates-section').innerHTML = `
      <div class="date-group expanded">
        <div class="date-items" style="max-height:none;">
          ${buildHistoryItem('debate-ddd444', '测试话题D')}
        </div>
      </div>
    `;

    document.querySelector('[data-debate-id="debate-ddd444"].delete-debate-btn').click();
    await new Promise(r => setTimeout(r, 50));

    expect(document.querySelectorAll('.history-item').length).toBe(1);
    expect(document.querySelector('.history-item-topic').textContent).toBe('测试话题D');
  });

  it('asks for confirmation before deleting', () => {
    document.getElementById('history-debates-section').innerHTML = `
      <div class="date-group expanded">
        <div class="date-items" style="max-height:none;">
          ${buildHistoryItem('debate-eee555', '测试话题E')}
        </div>
      </div>
    `;

    document.querySelector('[data-debate-id="debate-eee555"].delete-debate-btn').click();

    expect(window.confirm).toHaveBeenCalledWith(
      '确定要删除这场辩论记录吗？此操作不可撤销。'
    );
  });

  it('does nothing when user cancels confirmation', async () => {
    window.confirm.mockReturnValueOnce(false);

    document.getElementById('history-debates-section').innerHTML = `
      <div class="date-group expanded">
        <div class="date-items" style="max-height:none;">
          ${buildHistoryItem('debate-fff666', '测试话题F')}
        </div>
      </div>
    `;

    document.querySelector('[data-debate-id="debate-fff666"].delete-debate-btn').click();
    await new Promise(r => setTimeout(r, 50));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(document.querySelectorAll('.history-item').length).toBe(1);
  });

  it('removes empty date group when last item is deleted', async () => {
    document.getElementById('history-debates-section').innerHTML = `
      <div class="date-group expanded">
        <div class="date-header"><span class="date-label">今天</span></div>
        <div class="date-items" style="max-height:none;">
          ${buildHistoryItem('debate-ggg777', '唯一一场')}
        </div>
      </div>
    `;

    expect(document.querySelectorAll('.date-group').length).toBe(1);

    document.querySelector('[data-debate-id="debate-ggg777"].delete-debate-btn').click();
    await new Promise(r => setTimeout(r, 50));

    expect(document.querySelectorAll('.date-group').length).toBe(0);
    expect(document.getElementById('history-empty').classList.contains('hidden')).toBe(false);
  });

  it('shows empty state when all items are gone', async () => {
    document.getElementById('history-debates-section').innerHTML = `
      <div class="date-group expanded">
        <div class="date-items" style="max-height:none;">
          ${buildHistoryItem('debate-hhh888', '最后一场')}
        </div>
      </div>
    `;

    const emptyEl = document.getElementById('history-empty');
    expect(emptyEl.classList.contains('hidden')).toBe(true);

    document.querySelector('[data-debate-id="debate-hhh888"].delete-debate-btn').click();
    await new Promise(r => setTimeout(r, 50));

    expect(document.querySelectorAll('.history-item').length).toBe(0);
    expect(emptyEl.classList.contains('hidden')).toBe(false);
  });
});
