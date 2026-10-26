(() => {
  const $ = (q, r = document) => r.querySelector(q);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

  const qs = new URLSearchParams(location.search);
  const order = qs.get('order') || '';
  let chat, ws, startedAt = 0, seenEvents = new Set(), seenArtifacts = new Set();

  function sanitizeOrder(v) { v = String(v || '').trim(); return /^[A-Za-z0-9_.-]{4,64}$/.test(v) ? v : '' }
  function tech(label, payload) { /* debug log hook */ }
  function money(v) { return Number(v || 0).toLocaleString('ru-RU', { maximumFractionDigits: 2 }) + ' ₽' }
  function fmt(ms) {
    let s = Math.max(0, ms / 1000), m = Math.floor(s / 60);
    return String(m).padStart(2, '0') + ':' + (s - m * 60).toFixed(1).padStart(4, '0');
  }

  function setStatus(t) { const el = $('#status'); if (el) el.textContent = t || 'ready' }

  async function loadOrder() {
    if (!order) return;
    try {
      const r = await fetch('/api/orders/' + encodeURIComponent(order), { cache: 'no-store' });
      if (!r.ok) return;
      const j = await r.json();
      if (!j.ok) return;
      const o = j.order;
      $('#title').textContent = o.title || 'Jobsy Agent';
      $('#sub').textContent = 'Заказ ' + o.number + ' · агент с инструментами';
      $('#orderName').textContent = o.title || o.slug;
      $('#orderMeta').textContent = o.slug + ' · ' + (o.price_rub ? money(o.price_rub) : 'цена по тарифу');
      $('#orderCard').hidden = false;
      setStatus(o.status || 'new');
      // render recent events
      const box = $('#events');
      const evs = (j.events || []).slice(-30);
      box.innerHTML = evs.map(e => {
        const d = e.data || {};
        const label = e.label || e.event_type;
        const txt = d.text || (d.tool ? `инструмент ${d.tool}` : label);
        return `<div style="margin:4px 0"><span style="color:#7d899c">${e.created_at.slice(11,16)}</span> ${esc(txt)}</div>`;
      }).join('') || '<div style="color:#7d899c">Пока нет сообщений</div>';
      box.scrollTop = box.scrollHeight;
      // artifacts
      const arts = j.artifacts || [];
      for (const a of arts) renderArtifact(a);
      if (o.status === 'done') {
        $('#msg').disabled = true; $('#send').disabled = true;
      }
    } catch (_) { }
  }

  function artifactUrl(a) { return '/api/orders/' + encodeURIComponent(order) + '/artifacts/' + encodeURIComponent(a.artifact_id) }

  function renderArtifact(a) {
    const id = String(a.artifact_id || ''); if (!id || seenArtifacts.has(id)) return;
    seenArtifacts.add(id);
    const u = artifactUrl(a), mime = String(a.mime || '');
    let row;
    if (mime.startsWith('image/')) {
      row = chat.add('agent', 'Готово.', { image: u, extra: `<div class="actions"><a href="${u}" target="_blank">Скачать</a></div>` });
    } else if (mime.startsWith('audio/')) {
      row = chat.add('agent', 'Готов аудиорезультат: ' + esc(a.filename || 'audio.mp3'), { extra: `<audio controls src="${u}"></audio><div class="actions"><a href="${u}" download>Скачать MP3</a></div>` });
    } else {
      row = chat.add('agent', 'Готов результат: ' + esc(a.filename), { extra: `<div class="actions"><a href="${u}" target="_blank">Открыть</a></div>` });
    }
    chat.forceFollow();
  }

  async function loadEvents() {
    if (!order) return;
    try {
      const r = await fetch('/api/orders/' + encodeURIComponent(order) + '/events?limit=100', { cache: 'no-store' });
      if (!r.ok) return;
      const evs = await r.json();
      for (const ev of evs) {
        const type = String(ev.event_type || '');
        const key = String(ev.id || '') || type + '|' + (ev.label || '');
        if (seenEvents.has(key)) continue;
        seenEvents.add(key);
        const d = ev.data || {};
        if (type === 'runtime.text') {
          const piece = String(d.text || '');
          if (piece) { chat.hideTyping(); chat.appendStream(piece); }
        } else if (type === 'runtime.tool') {
          chat.status('Инструмент: ' + String(d.tool || 'шаг'));
        } else if (type === 'job.completed') {
          chat.add('agent', 'Заказ завершён. Результат готов.');
          $('#msg').disabled = true; $('#send').disabled = true;
          loadOrder();
        } else if (type === 'job.failed') {
          chat.add('agent', 'Ошибка выполнения: ' + String(d.error || ''));
        } else if (type === 'runtime.waiting') {
          chat.add('agent', 'Агент уточняет: ' + String(d.text || ''));
        } else if (type === 'artifact.created' && d.artifact_id) {
          renderArtifact({ ...d, mime: d.mime || '' });
        }
      }
    } catch (_) { }
  }

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = new URL(proto + '//' + location.host + '/api/orders/' + encodeURIComponent(order) + '/stream');
    ws = new WebSocket(wsUrl.toString());
    ws.onopen = () => { setStatus('connected'); loadEvents(); };
    ws.onclose = () => { setStatus('offline'); setTimeout(connect, 2000) };
    ws.onmessage = e => {
      let r = {};
      try { r = JSON.parse(e.data) } catch (_) { r = { text: e.data } }
      const type = String(r.event_type || r.type || '');
      const d = r.data || {};
      if (type === 'runtime.text') {
        const piece = String(d.text || '');
        if (piece) { chat.hideTyping(); chat.appendStream(piece); }
      } else if (type === 'job.completed') {
        chat.add('agent', 'Заказ завершён. Результат готов.');
        $('#msg').disabled = true; $('#send').disabled = true;
        loadOrder();
      } else if (type === 'job.failed') {
        chat.add('agent', 'Ошибка: ' + String(d.error || ''));
      } else if (type === 'artifact.created' && d.artifact_id) {
        renderArtifact({ ...d, mime: d.mime || '' });
      }
    };
  }

  async function sendMsg() {
    const input = $('#msg');
    const text = String(input.value || '').trim();
    if (!text) return;
    input.value = '';
    chat.add('user', text);
    try {
      const r = await fetch('/api/orders/' + encodeURIComponent(order) + '/message', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ text })
      });
      if (!r.ok) { chat.add('agent', 'Не удалось отправить сообщение'); return }
    } catch (err) { chat.add('agent', 'Ошибка сети: ' + err.message) }
  }

  function init() {
    chat = new NativeAgentChat($('#chatbox'), { placeholder: 'Опишите задачу для агента…', markdown: true });
    chat.scroll = $('#chatbox').querySelector('.nc-scroll');
    $('#send').onclick = sendMsg;
    $('#msg').onkeypress = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMsg() } };
    loadOrder();
    if (order) connect();
    if (!order || order === '') {
      $('#emptyChat').hidden = false;
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
