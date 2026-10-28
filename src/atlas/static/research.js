// All source/provider text enters the DOM through textContent, never HTML.
const node = (tag, text, className) => {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
};
const failure = (error) => error instanceof TypeError ? 'Could not reach Atlas. Please try again.' : error.message;
const research = {
  async open(workspace, signal) {
    const root = $('research');
    root.replaceChildren();
    const base = `/workspaces/${workspace.id}`;
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
