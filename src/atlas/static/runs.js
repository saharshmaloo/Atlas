async function runLibrary(root, base, signal) {
  const section = node('section'); section.id = 'research-runs';
  const form = node('form');
  const label = node('label', 'Research objective'); label.htmlFor = 'run-objective';
  const input = node('input'); input.id = 'run-objective'; input.required = true; input.maxLength = 500;
  const button = node('button', 'Create research run', 'primary');
  const status = node('p'); status.setAttribute('role', 'status');
  const list = node('div'); list.id = 'run-list';
  form.append(label, input, button, status);
  section.append(node('h3', 'Research runs'), node('p', 'Run saved-evidence steps with durable progress and execution budgets. Creation queues work; execute it here or with the worker.'), form, list);
  root.append(section);
  form.onsubmit = async event => {
    event.preventDefault(); if (button.disabled) return;
    if (!input.value.trim()) { input.setCustomValidity('Enter an objective.'); input.reportValidity(); return; }
    button.disabled = true;
    try {
      const run = await api(`${base}/runs`, {method: 'POST', signal, headers: {'Content-Type': 'application/json'}, body: JSON.stringify({objective: input.value.trim()})});
      if (!signal.aborted) location.hash = `${base}/runs/${run.id}`;
    } catch (error) { if (!signal.aborted) status.textContent = failure(error); }
    finally { button.disabled = false; }
  };
  input.oninput = () => input.setCustomValidity('');
  try {
    const items = await api(`${base}/runs?limit=20`, {signal});
    if (signal.aborted) return;
    list.replaceChildren(...items.map(run => {
      const row = node('p'); const link = node('a', `${run.objective} · ${run.status}`, 'text-link');
      link.href = `#${base}/runs/${run.id}`; row.append(link); return row;
    }));
    if (!items.length) list.textContent = 'No research runs yet.';
  } catch (error) { if (!signal.aborted) list.textContent = failure(error); }
}

async function runView(root, base, id, signal) {
  const url = `${base}/runs/${id}`;
  const back = node('a', '← Workspace research', 'back text-link'); back.href = `#${base}`;
  const content = node('div'); content.id = 'run-detail';
  const status = node('p'); status.setAttribute('role', 'status');
  const events = node('ol'); events.id = 'run-events';
  root.append(back, content, status, node('h3', 'Progress events'), events);
  let pending = false, stream, serial = 0, lastEvent = 0;
  function render(run) {
    content.replaceChildren(node('h3', run.objective), node('p', `Run status: ${run.status}`),
      node('p', `Tools: ${run.tool_calls}/${run.budgets.max_tool_calls} · Model calls reserved: ${run.model_calls_reserved}/${run.budgets.max_model_calls} · Tokens reserved: ${run.tokens_reserved}/${run.budgets.max_model_tokens}`),
      node('p', `Attempts per task: ${run.budgets.max_attempts} · Concurrency: ${run.budgets.max_concurrency} · Time limit: ${run.budgets.max_seconds}s${run.deadline_at ? ' · Deadline: ' + new Date(run.deadline_at).toLocaleString() : ''}`));
    for (const task of run.tasks) {
      const row = node('article', undefined, 'claim');
      row.append(node('h4', `${task.position + 1}. ${task.kind}: ${task.status}`), node('p', `Attempts: ${task.attempt}`));
      if (task.error) row.append(node('p', task.error));
      if (task.output?.answer_id) {
        const link = node('a', 'Open saved answer', 'text-link'); link.href = `#${base}/answers/${task.output.answer_id}`; row.append(link);
      }
      content.append(row);
    }
    function action(label, name) {
      const button = node('button', label, 'secondary'); button.disabled = pending;
      button.onclick = async () => {
        if (pending) return; pending = true; render(run); status.textContent = 'Working…';
        try {
          const result = await api(`${url}/${name}`, {method: 'POST', signal});
          if (!signal.aborted) { status.textContent = ''; run = result.run || result; if (name === 'resume') { stream?.close(); connect(); } }
        } catch (error) { if (!signal.aborted) status.textContent = failure(error); }
        finally { pending = false; if (!signal.aborted) render(run); }
      };
      content.append(button);
    }
    if (run.status === 'queued' && run.tasks.every(t => t.attempt === 0)) action('Plan saved-evidence steps', 'plan');
    if (['queued', 'running'].includes(run.status)) action('Run next task', 'step');
    if (['queued', 'running', 'failed'].includes(run.status)) action('Cancel run', 'cancel');
    if (['cancelled', 'failed'].includes(run.status)) action('Resume run', 'resume');
    if (!['queued', 'running'].includes(run.status) && lastEvent >= run.event_seq) stream?.close();
    else if (stream?.readyState === EventSource.CLOSED) connect();
  }
  async function refresh() {
    const current = ++serial;
    try {
      const run = await api(url, {signal});
      if (!signal.aborted && current === serial) render(run);
    } catch (error) { if (!signal.aborted) status.textContent = failure(error); }
  }
  await refresh();
  if (signal.aborted) return;
  function connect() {
  stream = new EventSource(`${url}/events/stream?after=${lastEvent}`);
  stream.addEventListener('progress', event => {
    if (signal.aborted) return;
    const item = JSON.parse(event.data);
    if (item.sequence <= lastEvent) return;
    lastEvent = item.sequence;
    events.append(node('li', `${item.sequence}. ${item.kind}${item.data.duration_ms !== undefined ? ' · ' + item.data.duration_ms + ' ms' : ''}`));
    while (events.children.length > 100) events.firstChild.remove();
    refresh();
  });
  stream.onerror = () => { if (!signal.aborted) status.textContent = 'Progress connection interrupted; reconnecting automatically.'; };
  }
  connect();
  signal.addEventListener('abort', () => stream.close(), {once: true});
}
