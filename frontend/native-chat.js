(() => {
  const $ = (q, r = document) => r.querySelector(q);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const tm = () => new Date().toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit'});

  function markdownHtml(value) {
    const lines = esc(value).replace(/\r/g, '').split('\n');
    let out = '', list = '';
    const close = () => { if (list) { out += `</${list}>`; list = '' } };
    const inline = s => s.replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\*(.+?)\*/g, '<em>$1</em>');
    for (const raw of lines) {
      const line = raw.trim();
      if (!line) { close(); continue }
      const h = line.match(/^(#{1,3})\s+(.+)$/);
      if (h) { close(); const tag = 'h' + (h[1].length + 1); out += `<${tag}>${inline(h[2])}</${tag}>`; continue }
      const bullet = line.match(/^[-*]\s+(.+)$/), number = line.match(/^\d+[.)]\s+(.+)$/);
      if (bullet || number) {
        const kind = bullet ? 'ul' : 'ol';
        if (list !== kind) { close(); list = kind; out += `<${kind}>` }
        out += `<li>${inline((bullet || number)[1])}</li>`;
        continue
      }
      close();
      out += `<p>${inline(line)}</p>`;
    }
    close();
    return out;
  }

  class NativeAgentChat {
    constructor(root, opts = {}) {
      this.root = root; this.opts = opts; this.lastRole = null;
      this.messages = []; this.pending = []; this.typingEl = null;
      this.actionSets = new Map(); this.selectedPreset = null;
      this.followBottom = true; this._autoScrolling = false;
      this._toolRows = {};
      this.build(); this.bindAutoScroll();
    }

    build() {
      this.root.innerHTML = `
        <div class="nc-scroll"><div class="nc-stream"></div></div>
        <div class="nc-composer-wrap"><div class="nc-composer">
          <textarea class="nc-input" rows="1" placeholder="${esc(this.opts.placeholder || 'Напишите сообщение…')}"></textarea>
          <button class="nc-send" type="button" aria-label="Отправить">➤</button>
        </div></div>`;
      this.stream = $('.nc-stream', this.root);
      this.input = $('.nc-input', this.root);
      $('.nc-send', this.root).onclick = () => this.submit();
      this.input.onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.submit() } };
      this.input.oninput = () => { this.input.style.height = '34px'; this.input.style.height = Math.min(this.input.scrollHeight, 120) + 'px' };
    }

    add(role, text, opt = {}) {
      this.hideTyping();
      const same = this.lastRole === role && !opt.forceHead;
      const row = document.createElement('div');
      row.className = `nc-row ${role}${same ? ' same' : ''}`;
      const media = opt.image ? `<img class="nc-media" src="${esc(opt.image)}" alt="">` : '';
      const body = text ? `<span class="nc-caption">${this.renderText(role, text)}</span>` : '';
      row.innerHTML = `${role === 'agent' ? '<div class="nc-avatar">F</div>' : ''}<div class="nc-col"><div class="nc-name">${role === 'user' ? 'Вы' : 'Агент'}</div><div class="nc-bubble">${media}${body}<span class="nc-time">${esc(opt.time || tm())}${role === 'user' ? ' ✓' : ''}</span>${opt.extra || ''}</div></div>`;
      this.lastRole = role;
      this.messages.push({ role, text, ...opt });
      this._append(row);
      return row;
    }

    renderText(role, text) {
      return this.opts.markdown && role === 'agent' ? markdownHtml(text) : esc(text).replace(/\n/g, '<br>');
    }

    _append(node) {
      this.stream.insertBefore(node, this.stream.lastElementChild);
      this.scrollBottom();
      return node;
    }

    beginStream(role = 'agent') {
      this.hideTyping();
      const row = this.add(role, '');
      row.classList.add('nc-streaming');
      const cap = document.createElement('span');
      cap.className = 'nc-caption';
      row.querySelector('.nc-bubble').insertBefore(cap, row.querySelector('.nc-bubble').firstChild);
      this.streamRow = row; this.streamRole = role; this.streamText = '';
      this.forceFollow();
      return row;
    }

    appendStream(text) {
      if (!text) return;
      if (!this.streamRow) this.beginStream(this.streamRole || 'agent');
      this.streamText += text;
      const cap = this.streamRow && this.streamRow.querySelector('.nc-caption');
      if (cap) cap.innerHTML = this.renderText(this.streamRole, this.streamText);
      this.scrollBottom();
    }

    endStream(finalText) {
      if (!this.streamRow) return;
      this.streamRow.classList.remove('nc-streaming');
      const shown = finalText != null && finalText !== '' ? finalText : this.streamText;
      const cap = this.streamRow.querySelector('.nc-caption');
      if (cap && shown) cap.innerHTML = this.renderText(this.streamRole, shown);
      this.streamRow = null; this.streamText = '';
    }

    addImage(role, url, caption) { return this.add(role, caption || '', { image: url }) }
    status(text) { const x = document.createElement('div'); x.className = 'nc-status'; x.innerHTML = `<span>${esc(text)}</span>`; this.lastRole = null; return this._append(x) }
    hideTyping() { this.typingEl?.remove(); this.typingEl = null }
    forceFollow() { this.followBottom = true }
    scrollBottom(force = false) {
      if (!this.scroll) return;
      if (force) this.followBottom = true;
      if (!this.followBottom) return;
      const run = () => { this.scroll.scrollTop = Math.max(0, this.scroll.scrollHeight - this.scroll.clientHeight); };
      run(); setTimeout(run, 30); setTimeout(run, 120); setTimeout(run, 320);
    }
    bindAutoScroll() {
      const nearBottom = () => (this.scroll.scrollHeight - this.scroll.clientHeight - this.scroll.scrollTop) < 96;
      this.scroll.addEventListener('scroll', () => { if (!this._autoScrolling) this.followBottom = nearBottom() }, { passive: true });
    }
    get scroll() { return this.root.querySelector('.nc-scroll') }
    get streamEl() { return this.root.querySelector('.nc-stream') }
    submit() {
      const text = this.input.value.trim();
      if (!text) return;
      this.input.value = ''; this.input.style.height = '34px';
      if (this.opts.onSubmit) this.opts.onSubmit(text);
    }
    actions(items, opt = {}) {
      if (!items?.length) return;
      const id = 'a' + Date.now() + Math.random();
      const box = document.createElement('div');
      box.className = 'actions'; box.dataset.actionSet = id;
      items.forEach((a, i) => {
        const b = document.createElement('button');
        b.className = (a.primary || i === 0 && opt.primaryFirst) ? 'primary' : '';
        b.textContent = a.label;
        b.onclick = () => {
          box.querySelectorAll('button').forEach(x => x.remove()); box.remove();
          if (opt.echo !== false && a.echo !== false) this.add('user', a.echo || a.label);
          a.onClick?.(a);
        };
        box.appendChild(b);
      });
      this._append(box);
    }
  }
  window.NativeAgentChat = NativeAgentChat;
})();
