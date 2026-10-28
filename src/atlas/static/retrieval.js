function retrievalSelect(form, id, value = 'keyword') {
  const label = node('label', 'Retrieval'); label.htmlFor = id;
  const select = node('select'); select.id = id;
  for (const [key, text] of [['keyword', 'Keyword'], ['hybrid', 'Keyword + vector']]) {
    const option = node('option', text); option.value = key; select.append(option);
  }
  select.value = value;
  form.append(label, select);
  return select;
}

function embeddingControls(root, base, signal) {
  const section = node('section'); section.id = 'embedding-controls';
  const button = node('button', 'Generate embeddings', 'secondary');
  const status = node('p'); status.setAttribute('role', 'status');
  section.append(button, node('p', 'Optional vector retrieval requires a server-configured embedding provider. Each click processes up to 16 pending passages.'), status);
  root.append(section);
  button.onclick = async () => {
    if (button.disabled) return;
    button.disabled = true; status.textContent = 'Generating embeddings…';
    try {
      const result = await api(`${base}/embeddings`, {method: 'POST', signal});
      if (!signal.aborted) status.textContent = `${result.embedded} of ${result.total} passages embedded. ${result.complete ? 'Complete.' : 'Click again to continue.'}`;
    } catch (error) { if (!signal.aborted) status.textContent = failure(error); }
    finally { button.disabled = false; }
  };
}
