async function sourceVersions(root, base, source, signal, params) {
  const section = node('section'); section.id = 'source-versions';
  const status = node('p'); status.setAttribute('role', 'status');
  const form = node('form');
  let file;
  if (source.kind !== 'web') {
    const label = node('label', `Replacement ${source.kind === 'pdf' ? '.pdf' : '.txt'} file (up to 1 MiB)`); label.htmlFor = 'version-file';
    file = node('input'); file.type = 'file'; file.id = 'version-file'; file.accept = source.kind === 'pdf' ? '.pdf' : '.txt'; file.required = true;
    form.append(label, file);
  }
  const button = node('button', source.kind === 'web' ? 'Refresh webpage' : 'Upload new version', 'secondary');
  form.append(button, status);
  const list = node('div'); list.id = 'version-list';
  const previous = node('button', 'Previous versions', 'secondary');
  const next = node('button', 'Next versions', 'secondary');
  const nav = node('nav'); nav.setAttribute('aria-label', 'Source version pages'); nav.append(previous, next);
  section.append(node('h3', 'Source versions'), node('p', 'A new version preserves this original and its existing citations.'), form, list, nav); root.append(section);
  const context = new URLSearchParams(params.has('q') ? {q: params.get('q'), mode: params.get('mode') || 'keyword'} : {});
  const target = id => `#${base}/sources/${id}?${context}`;
  form.onsubmit = async event => {
    event.preventDefault(); if (button.disabled) return;
    let path, options;
    if (source.kind === 'web') {
      path = `${base}/sources/web`;
      options = {headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url: source.original_uri, previous_source_id: source.id})};
    } else {
      const selected = file.files[0];
      const extension = source.kind === 'pdf' ? '.pdf' : '.txt';
      if (!selected || !selected.name.toLowerCase().endsWith(extension) || !selected.size || selected.size > 1048576) {
        status.textContent = `Choose a nonempty ${extension} file of at most 1 MiB.`; return;
      }
      const body = new FormData(); body.append('file', selected);
      path = source.kind === 'pdf' ? `${base}/sources/pdf?previous_source_id=${source.id}` : `${base}/sources/${source.id}/versions`;
      options = {body};
    }
    button.disabled = true; if (file) file.disabled = true; status.textContent = 'Saving new version…';
    try {
      const replacement = await api(path, {...options, method: 'POST', signal});
      if (!signal.aborted) location.hash = target(replacement.id);
    } catch (error) { if (!signal.aborted) status.textContent = failure(error); }
    finally { button.disabled = false; if (file) file.disabled = false; }
  };
  let offset = 0;
  async function load() {
    previous.disabled = next.disabled = true;
    try {
      const versions = await api(`${base}/sources/${source.id}/versions?offset=${offset}`, {signal});
      if (signal.aborted) return;
      list.replaceChildren(...versions.map(version => {
        const row = node('p'); const link = node('a', `Version ${version.version}: ${version.title}`, 'text-link');
        link.href = target(version.id); row.append(link); return row;
      }));
      previous.disabled = offset === 0; next.disabled = versions.length < 50;
    } catch (error) { if (!signal.aborted) status.textContent = failure(error); }
  }
  previous.onclick = () => { offset -= 50; load(); }; next.onclick = () => { offset += 50; load(); };
  await load();
}
