// All source/provider text enters the DOM through textContent, never HTML.
const node = (tag, text, className) => {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
};
const failure = (error) => error instanceof TypeError ? 'Could not reach Atlas. Please try again.' : error.message;
const research = {
  async saved(root, base, id, signal) {
    root.textContent = 'Loading saved answer…';
    const answer = await api(`${base}/answers/${id}`, {signal});
    if (signal.aborted) return;
    root.replaceChildren();
    const back = node('a', '← Workspace history', 'back text-link'); back.href = `#${base}`;
    root.append(back);
    this.question(root, base, signal, answer);
  },
  async history(root, base, signal) {
    const section = node('section'); section.id = 'history';
    const list = node('div'); list.id = 'answer-history';
    const previous = node('button', 'Previous answers', 'secondary');
    const next = node('button', 'Next answers', 'secondary');
    const pager = node('nav'); pager.setAttribute('aria-label', 'Answer history pages'); pager.append(previous, next);
    section.append(node('h3', 'Saved answer history'), list, pager); root.append(section);
    let offset = 0, listing;
    async function load() {
      listing?.abort(); listing = new AbortController();
      const local = listing.signal;
      previous.disabled = next.disabled = true; list.textContent = 'Loading history…';
      try {
        const items = await api(`${base}/answers?limit=11&offset=${offset}`, {signal: local});
        if (signal.aborted || local.aborted) return;
        list.replaceChildren(...items.slice(0, 10).map(answer => {
          const row = node('p');
          const link = node('a', answer.question, 'text-link'); link.href = `#${base}/answers/${answer.id}`;
          const time = node('time', new Date(answer.created_at).toLocaleString()); time.dateTime = answer.created_at;
          row.append(link, node('span', ` · ${answer.status === 'answered' ? 'Answered' : 'Insufficient evidence'} · `), time);
          return row;
        }));
        if (!items.length) list.textContent = 'No saved answers yet. Ask a question to start your history.';
        previous.disabled = offset === 0; next.disabled = items.length <= 10;
      } catch (error) {
        if (!signal.aborted && !local.aborted) {
          list.replaceChildren(node('p', failure(error)));
          const retry = node('button', 'Retry history', 'secondary'); retry.onclick = load; list.append(retry);
        }
      }
    }
    signal.addEventListener('abort', () => listing?.abort(), {once: true});
    previous.onclick = () => { offset -= 10; load(); };
    next.onclick = () => { offset += 10; load(); };
    await load();
  },

  citation(base, citation) {
    const dialog = $('evidence-dialog');
    const title = node('h2', citation.source_title); title.id = 'evidence-title';
    const close = node('button', 'Close evidence', 'secondary'); close.autofocus = true;
    close.onclick = () => dialog.close();
    const link = node('a', 'Open current source', 'text-link');
    link.href = `#${base}/sources/${citation.source_id}?${new URLSearchParams({passage: citation.id, position: citation.position})}`;
    link.onclick = () => dialog.close();
    dialog.replaceChildren(node('p', 'SAVED CITATION SNAPSHOT', 'eyebrow'), title,
      node('p', `Passage ${citation.position + 1} · Unicode characters ${citation.start_char}–${citation.end_char} (exclusive end)`),
      node('p', citation.id, 'mono'),
      node('p', `Source version ${citation.source_version || 1} · ${citation.source_kind || 'text'}${citation.locations?.length ? ' · ' + citation.locations.map(loc => 'page ' + loc.page).join(', ') : ''}`), node('pre', citation.text, 'source-text'),
      node('p', 'This evidence was saved with the answer. Citation membership does not establish semantic support for the claim.'),
      link, node('p', 'The current source may have changed or be unavailable.'), close);
    dialog.showModal();
  },
  answer(root, base, answer) {
    root.replaceChildren(); root.dataset.answerId = answer.id;
    root.append(node('h3', answer.question), node('p', `${answer.status === 'answered' ? 'Answered' : 'Insufficient evidence'} · ${new Date(answer.created_at).toLocaleString()}`));
    if (answer.status === 'insufficient_evidence') root.append(node('p', 'Insufficient evidence in the saved passages. Add sources or try another question.'));
    if (answer.provenance) root.append(node('p', `Generated with ${answer.provenance.provider || 'no provider'}${answer.provenance.model ? ' / ' + answer.provenance.model : ''} · ${answer.provenance.retrieval} · ${answer.provenance.duration_ms} ms`));
    answer.claims.forEach(claim => {
      const row = node('article', undefined, 'claim'); row.append(node('p', claim.text));
      claim.passage_ids.forEach(id => {
        const citation = answer.citations.find(item => item.id === id);
        const link = node('button', `Evidence: ${citation.source_title} · passage ${citation.position + 1}`, 'secondary');
        link.onclick = () => this.citation(base, citation);
        row.append(link);
      });
      root.append(row);
    });
    root.append(node('p', 'Citation IDs are validated against retrieved evidence. They do not establish that the evidence semantically supports a claim.'));
  },
  question(root, base, signal, saved) {
    const section = node('section'); section.id = 'questions';
    const form = node('form');
    const label = node('label', 'Question about saved evidence'); label.htmlFor = 'question';
    const input = node('input'); input.id = 'question'; input.required = true; input.maxLength = 500;
    const submit = node('button', 'Ask question', 'primary');
    const message = node('p'); message.setAttribute('role', 'status');
    const answer = node('div'); answer.id = 'answer';
    form.append(label, input);
    const retrieval = retrievalSelect(form, 'question-retrieval', saved?.provenance?.retrieval.startsWith('hybrid') ? 'hybrid' : 'keyword');
    form.append(submit, message);
    section.append(node('h3', 'Ask your sources'), form, answer); root.append(section);
    if (saved) { input.value = saved.question; this.answer(answer, base, saved); supportView(answer, base, saved, signal); }
    let pending = false, requestKey, keyQuestion;
    input.oninput = () => input.setCustomValidity('');
    form.onsubmit = async event => {
      event.preventDefault();
      if (pending) return;
      const question = input.value.trim();
      if (!question || question.includes('\0')) { input.setCustomValidity('Enter a question without NUL characters.'); input.reportValidity(); return; }
      const signature = JSON.stringify([question, retrieval.value]);
      if (keyQuestion !== signature) { keyQuestion = signature; requestKey = crypto.randomUUID(); }
      pending = true; submit.disabled = true; answer.replaceChildren(); message.textContent = 'Finding evidence and preparing an answer…';
      try {
        const result = await api(`${base}/answers`, {method: 'POST', signal,
          headers: {'Content-Type': 'application/json', 'Idempotency-Key': requestKey}, body: JSON.stringify({question, retrieval: retrieval.value})});
        if (signal.aborted) return;
        location.hash = `${base}/answers/${result.id}`;
      } catch (error) {
        if (!signal.aborted) message.textContent = failure(error);
      } finally { pending = false; submit.disabled = false; }
    };
  },

  async search(root, base, params, signal) {
    const section = node('section'); section.id = 'search';
    const form = node('form');
    const label = node('label', 'Search saved passages'); label.htmlFor = 'search-query';
    const input = node('input'); input.id = 'search-query'; input.required = true; input.maxLength = 500;
    input.value = params.get('q') || '';
    const submit = node('button', 'Search', 'primary');
    const results = node('div'); results.id = 'search-results'; results.setAttribute('role', 'status');
    form.append(label, input);
    const retrieval = retrievalSelect(form, 'search-retrieval', params.get('mode') || 'keyword');
    form.append(submit);
    section.append(node('h3', 'Find evidence'), node('p', 'Keyword search covers generated passages. Ranking is not a confidence score.'), form, results);
    root.append(section);
    form.onsubmit = event => {
      event.preventDefault();
      const q = input.value.trim();
      if (!q || q.includes('\0')) { input.setCustomValidity('Enter a search query without NUL characters.'); input.reportValidity(); return; }
      const hash = `#${base}?${new URLSearchParams({q, mode: retrieval.value})}`;
      if (location.hash === hash) renderRoute(); else location.hash = hash;
    };
    input.oninput = () => input.setCustomValidity('');
    if (!input.value) return;
    submit.disabled = true; results.textContent = 'Searching…';
    try {
      const response = await api(`${base}/${retrieval.value === 'hybrid' ? 'hybrid-search' : 'search'}?${new URLSearchParams({q: input.value, limit: 50})}`, {signal});
      if (signal.aborted) return;
      const items = Array.isArray(response) ? response : response.results;
      results.replaceChildren(...items.map((passage, index) => {
        const row = node('article');
        const link = node('a', `${index + 1}. ${passage.source_title} · Passage ${passage.position + 1}`, 'text-link');
        link.href = `#${base}/sources/${passage.source_id}?${new URLSearchParams({q: input.value, mode: retrieval.value, passage: passage.id, position: passage.position})}`;
        row.append(link, node('p', `Characters ${passage.start_char}–${passage.end_char} · ${passage.id}`, 'mono'), node('pre', passage.text, 'source-text'));
        return row;
      }));
      if (!items.length) results.textContent = 'No matching passages. Try other keywords or generate source passages.';
    } catch (error) {
      if (!signal.aborted) results.textContent = failure(error);
    } finally { submit.disabled = false; }
  },

  async source(root, base, id, signal, params) {
    const back = node('a', '← Workspace sources', 'back text-link');
    back.href = `#${base}?${new URLSearchParams(params.has('q') ? {q: params.get('q'), mode: params.get('mode') || 'keyword'} : {})}`;
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
    root.replaceChildren(back, node('h3', source.title), node('p', `Source version ${source.version} · ${source.kind}${source.original_uri ? ' · ' + source.original_uri + ' · Retrieved ' + new Date(source.retrieved_at).toLocaleString() : ''}${source.kind === 'pdf' ? ' · Extracted Unicode text; offsets are not PDF byte offsets. Page spans: ' + source.locations.map(loc => `page ${loc.page}: ${loc.start_char}–${loc.end_char}`).join(', ') : ''}`), node('h4', source.kind === 'pdf' ? 'Extracted source text' : 'Original source text'), original,
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
    if (kind === 'answers') return this.saved(root, base, id, signal);
    const heading = node('h3', 'Sources');
    const form = node('form'); form.id = 'upload-form';
    const label = node('label', 'Upload a UTF-8 .txt or text-based .pdf file (up to 1 MiB)');
    label.htmlFor = 'source-file';
    const file = node('input');
    file.type = 'file'; file.id = 'source-file'; file.accept = '.txt,.pdf'; file.required = true;
    const submit = node('button', 'Upload source', 'primary');
    const message = node('p'); message.setAttribute('role', 'status');
    form.append(label, file, submit, message);
    const list = node('div'); list.id = 'source-list';
    const pager = node('nav'); pager.setAttribute('aria-label', 'Source pages');
    const previous = node('button', 'Previous sources', 'secondary');
    const next = node('button', 'Next sources', 'secondary');
    pager.append(previous, next);
    root.append(heading, form, list, pager);
    webUpload(root, base, signal);
    embeddingControls(root, base, signal);
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
      if (!selected || !/\.(txt|pdf)$/i.test(selected.name)) { message.textContent = 'Choose a .txt or .pdf file.'; return; }
      if (!selected.size || selected.size > 1048576) { message.textContent = 'Choose a nonempty file of at most 1 MiB.'; return; }
      pending = true; submit.disabled = file.disabled = true;
      message.textContent = 'Uploading…';
      const data = new FormData(); data.append('file', selected);
      try {
        await api(`${base}/sources${/\.pdf$/i.test(selected.name) ? '/pdf' : ''}`, {method: 'POST', body: data, signal});
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
    if (!signal.aborted) this.question(root, base, signal);
    if (!signal.aborted) await this.search(root, base, params, signal);
    if (!signal.aborted) await this.history(root, base, signal);
  },
};
