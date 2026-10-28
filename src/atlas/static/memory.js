function rememberControls(root, base, answer, signal) {
  if (!answer.claims.length) return;
  const button = node('button', 'Save claims to memory', 'secondary');
  const status = node('p'); status.setAttribute('role', 'status');
  root.append(button, status);
  button.onclick = async () => {
    if (button.disabled) return; button.disabled = true;
    try {
      const claims = await api(`${base}/answers/${answer.id}/remember`, {method: 'POST', signal});
      if (!signal.aborted) status.textContent = `${claims.length} interpretations saved with evidence assessments. They remain generated interpretations.`;
    } catch (error) { if (!signal.aborted) status.textContent = failure(error); }
    finally { button.disabled = false; }
  };
}

async function memoryLibrary(root, base, signal) {
  const section = node('section'); section.id = 'memory';
  const form = node('form'); const label = node('label', 'Search remembered interpretations'); label.htmlFor = 'memory-query';
  const input = node('input'); input.id = 'memory-query'; input.maxLength = 500;
  const submit = node('button', 'Search memory', 'secondary'); form.append(label, input, submit);
  const list = node('div'); list.id = 'memory-list';
  const status = node('p'); status.setAttribute('role', 'status');
  section.append(node('h3', 'Research memory'), node('p', 'Generated interpretations retain their original evidence and fallible assessments. Only current, supported, uncontested evidence can expand an answer.'), form, status, list);
  root.append(section);
  async function load() {
    submit.disabled = true;
    try {
      const items = await api(input.value.trim() ? `${base}/memory-search?${new URLSearchParams({q: input.value.trim()})}` : `${base}/claims?limit=20`, {signal});
      if (signal.aborted) return;
      list.replaceChildren(...items.map(claim => {
        const row = node('article', undefined, 'claim'); row.append(node('h4', claim.text), node('p', `Generated interpretation · ${claim.state} · ${claim.id}`));
        const answer = node('a', 'Original saved answer', 'text-link'); answer.href = `#${base}/answers/${claim.answer_id}`; row.append(answer);
        for (const edge of claim.evidence) {
          const button = node('button', `${edge.relation} · ${edge.verification_status} · ${edge.freshness}`, 'secondary');
          button.onclick = () => research.citation(base, edge.snapshot); row.append(button);
        }
        for (const relation of claim.relations) row.append(node('p', `${relation.kind}: ${relation.note}`));
        return row;
      }));
      if (!items.length) list.textContent = 'No remembered interpretations found.';
      status.textContent = '';
    } catch (error) { if (!signal.aborted) status.textContent = failure(error); }
    finally { submit.disabled = false; }
  }
  form.onsubmit = event => { event.preventDefault(); if (!submit.disabled) load(); };
  await load();
  if (signal.aborted) return;
  const relationForm = node('form');
  const from = node('input'); from.placeholder = 'New / first claim UUID'; from.required = true;
  const to = node('input'); to.placeholder = 'Earlier / second claim UUID'; to.required = true;
  const kind = node('select');
  for (const name of ['contradicts', 'supersedes']) { const option = node('option', name); option.value = name; kind.append(option); }
  const note = node('input'); note.required = true; note.maxLength = 1000;
  const save = node('button', 'Save claim relationship', 'secondary');
  for (const [text, control, id] of [['First claim ID', from, 'relation-from'], ['Second claim ID', to, 'relation-to'], ['Relationship', kind, 'relation-kind'], ['Reason for relationship', note, 'relation-note']]) {
    const label = node('label', text); label.htmlFor = id; control.id = id; relationForm.append(label, control);
  }
  relationForm.append(save); section.append(node('h4', 'Record a disagreement or supersession'), relationForm);
  relationForm.onsubmit = async event => {
    event.preventDefault(); if (save.disabled) return; save.disabled = true;
    try {
      await api(`${base}/claim-relations`, {method: 'POST', signal, headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({from_claim_id: from.value.trim(), to_claim_id: to.value.trim(), kind: kind.value, note: note.value.trim()})});
      if (!signal.aborted) { relationForm.reset(); await load(); }
    } catch (error) { if (!signal.aborted) status.textContent = failure(error); }
    finally { save.disabled = false; }
  };
}

async function openQuestions(root, base, signal) {
  const section = node('section'); section.id = 'open-questions';
  const form = node('form'); const label = node('label', 'Question to investigate later'); label.htmlFor = 'open-question';
  const input = node('input'); input.id = 'open-question'; input.required = true; input.maxLength = 500;
  const button = node('button', 'Save open question', 'secondary');
  const status = node('p'); status.setAttribute('role', 'status');
  const list = node('div');
  form.append(label, input, button); section.append(node('h3', 'Open questions'), form, status, list); root.append(section);
  async function load() {
    const questions = await api(`${base}/questions`, {signal}); if (signal.aborted) return;
    list.replaceChildren(...questions.map(question => {
      const row = node('article', undefined, 'claim'); row.append(node('h4', question.question), node('p', question.status));
      for (const update of question.updates) row.append(node('p', `${update.status}: ${update.note}`));
      const updateForm = node('form'); const note = node('input'); note.required = true; note.maxLength = 1000;
      const label = node('label', 'Resolution or reopening note'); note.id = `note-${question.id}`; label.htmlFor = note.id;
      const save = node('button', question.status === 'open' ? 'Resolve question' : 'Reopen question', 'secondary');
      updateForm.append(label, note, save); row.append(updateForm);
      updateForm.onsubmit = async event => {
        event.preventDefault(); if (save.disabled) return; save.disabled = true;
        try {
          await api(`${base}/questions/${question.id}/updates`, {method: 'POST', signal, headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({status: question.status === 'open' ? 'resolved' : 'open', note: note.value})});
          if (!signal.aborted) await load();
        } catch (error) { if (!signal.aborted) status.textContent = failure(error); }
        finally { save.disabled = false; }
      };
      return row;
    }));
  }
  form.onsubmit = async event => {
    event.preventDefault(); if (button.disabled) return; button.disabled = true;
    try {
      await api(`${base}/questions`, {method: 'POST', signal, headers: {'Content-Type': 'application/json'}, body: JSON.stringify({question: input.value})});
      if (!signal.aborted) { form.reset(); await load(); }
    } catch (error) { if (!signal.aborted) status.textContent = failure(error); }
    finally { button.disabled = false; }
  };
  try { await load(); } catch (error) { if (!signal.aborted) status.textContent = failure(error); }
}
