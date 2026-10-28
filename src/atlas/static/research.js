// All source/provider text enters the DOM through textContent, never HTML.
const node = (tag, text, className) => {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
};
const failure = (error) => error instanceof TypeError ? 'Could not reach Atlas. Please try again.' : error.message;
const research = {
  async source(root, base, id, signal, params) {
    const back = node('a', '← Workspace sources', 'back text-link');
    back.href = `#${base}`;
    root.append(back, node('p', 'Loading source…'));
    const [source, content] = await Promise.all([
      api(`${base}/sources/${id}`, {signal}), api(`${base}/sources/${id}/content`, {signal, text: true}),
    ]);
    if (signal.aborted) return;
    const original = node('pre', content, 'source-text'); original.id = 'source-text';
    const generate = node('button', 'Generate passages', 'primary');
    const message = node('p'); message.setAttribute('role', 'status');
    const passages = node('div'); passages.id = 'passages';
    const previous = node('button', 'Previous passages', 'secondary');
    const next = node('button', 'Next passages', 'secondary');
    const pager = node('nav'); pager.setAttribute('aria-label', 'Passage pages'); pager.append(previous, next);
    root.replaceChildren(back, node('h3', source.title), node('h4', 'Original source text'), original,
      node('h3', 'Passages'), node('p', 'Offsets count Unicode code points; the end offset is exclusive.'),
      generate, message, passages, pager);
    let offset = Math.floor(Math.max(0, Number(params.get('position')) || 0) / 10) * 10;
    let pending = false, listing;
    async function load() {
      listing?.abort(); listing = new AbortController();
      const local = listing.signal;
      previous.disabled = next.disabled = true;
      passages.textContent = 'Loading passages…';
      try {
        const items = await api(`${base}/sources/${id}/passages?limit=11&offset=${offset}`, {signal: local});
        if (signal.aborted || local.aborted) return;
        passages.replaceChildren(...items.slice(0, 10).map(passage => {
          const row = node('article'); row.id = `passage-${passage.id}`;
          row.append(node('h4', `Passage ${passage.position + 1} · characters ${passage.start_char}–${passage.end_char}`),
            node('p', passage.id, 'mono'), node('pre', passage.text, 'source-text'));
          if (params.get('passage') === passage.id) { row.className = 'selected'; row.tabIndex = -1; }
          return row;
        }));
        if (!items.length) passages.textContent = 'No passages yet. Generate passages to make this source searchable.';
        previous.disabled = offset === 0; next.disabled = items.length <= 10;
        const selected = passages.querySelector('.selected');
        selected?.focus();
      } catch (error) {
        if (!signal.aborted && !local.aborted) {
          passages.replaceChildren(node('p', failure(error)));
          const retry = node('button', 'Retry passages', 'secondary'); retry.onclick = load; passages.append(retry);
        }
      }
    }
    signal.addEventListener('abort', () => listing?.abort(), {once: true});
    previous.onclick = () => { offset -= 10; load(); };
    next.onclick = () => { offset += 10; load(); };
    generate.onclick = async () => {
      if (pending) return;
      pending = true; generate.disabled = true; message.textContent = 'Generating passages…';
      try {
        const result = await api(`${base}/sources/${id}/passages`, {method: 'POST', signal});
        if (signal.aborted) return;
        message.textContent = `${result.passage_count} passages available.`;
        await load();
      } catch (error) {
        if (!signal.aborted) message.textContent = failure(error);
      } finally { pending = false; generate.disabled = false; }
    };
    await load();
  },

  async open(workspace, signal, kind, id, params) {
    const root = $('research');
    root.replaceChildren();
    const base = `/workspaces/${workspace.id}`;
    if (kind === 'sources') return this.source(root, base, id, signal, params);
    const heading = node('h3', 'Sources');
    const form = node('form');
    const label = node('label', 'Upload a UTF-8 .txt file (up to 1 MiB)');
    label.htmlFor = 'source-file';
    const file = node('input');
    file.type = 'file'; file.id = 'source-file'; file.accept = '.txt'; file.required = true;
    const submit = node('button', 'Upload source', 'primary');
    const message = node('p'); message.setAttribute('role', 'status');
    form.append(label, file, submit, message);
    const list = node('div'); list.id = 'source-list';
    const pager = node('nav'); pager.setAttribute('aria-label', 'Source pages');
    const previous = node('button', 'Previous sources', 'secondary');
    const next = node('button', 'Next sources', 'secondary');
    pager.append(previous, next);
    root.append(heading, form, list, pager);
    let offset = 0, pending = false, listing;
    async function load() {
      listing?.abort(); listing = new AbortController();
      const local = listing.signal;
      list.textContent = 'Loading sources…';
      previous.disabled = next.disabled = true;
      try {
        const items = await api(`${base}/sources?limit=11&offset=${offset}`, {signal: local});
        if (signal.aborted || local.aborted) return;
        list.replaceChildren(...items.slice(0, 10).map(source => {
          const row = node('p');
          const link = node('a', source.title, 'text-link');
          link.href = `#/workspaces/${workspace.id}/sources/${source.id}`;
          row.append(link, node('span', ` · ${date(source.created_at)}`));
          return row;
        }));
        if (!items.length) list.textContent = 'No sources yet. Upload a document to begin.';
        previous.disabled = offset === 0;
        next.disabled = items.length <= 10;
      } catch (error) {
        if (!signal.aborted && !local.aborted) {
          list.replaceChildren(node('p', failure(error)));
          const retry = node('button', 'Retry sources', 'secondary');
          retry.onclick = load; list.append(retry);
        }
      }
    }
    signal.addEventListener('abort', () => listing?.abort(), {once: true});
    previous.onclick = () => { offset -= 10; load(); };
    next.onclick = () => { offset += 10; load(); };
    form.onsubmit = async event => {
      event.preventDefault();
      if (pending) return;
      const selected = file.files[0];
      if (!selected || !/\.txt$/i.test(selected.name)) { message.textContent = 'Choose a .txt file.'; return; }
      if (!selected.size || selected.size > 1048576) { message.textContent = 'Choose a nonempty file of at most 1 MiB.'; return; }
      pending = true; submit.disabled = file.disabled = true;
      message.textContent = 'Uploading…';
      const data = new FormData(); data.append('file', selected);
      try {
        await api(`${base}/sources`, {method: 'POST', body: data, signal});
        if (signal.aborted) return;
        form.reset(); message.textContent = 'Source uploaded.';
        offset = 0; await load();
      } catch (error) {
        if (!signal.aborted) message.textContent = failure(error);
      } finally {
        pending = false; submit.disabled = file.disabled = false;
      }
    };
    await load();
  },
};
