async function supportView(root, base, answer, signal) {
  if (!answer.claims.length) return;
  const section = node('section'); section.id = 'claim-support';
  const button = node('button', 'Check claim support', 'secondary'); button.disabled = true;
  const status = node('p'); status.setAttribute('role', 'status');
  const list = node('div');
  section.append(node('h3', 'Claim support judgments'), node('p', 'Judgments are fallible assessments of the saved evidence, not proof.'), button, status, list);
  root.append(section);
  const url = `${base}/answers/${answer.id}/verifications`;
  function show(record) {
    list.replaceChildren(...record.judgments.map(item => node('p', `Claim ${item.claim_index + 1}: ${item.status} — ${item.explanation}`)));
    status.textContent = `${record.verifier} · ${new Date(record.created_at).toLocaleString()}`;
  }
  button.onclick = async () => {
    if (button.disabled) return;
    button.disabled = true; status.textContent = 'Checking claim support…';
    try {
      const result = await api(url, {method: 'POST', signal});
      if (!signal.aborted) show(result);
    } catch (error) { if (!signal.aborted) status.textContent = failure(error); }
    finally { button.disabled = false; }
  };
  try {
    const results = await api(url, {signal});
    if (signal.aborted) return;
    if (results.length) show(results[0]); else status.textContent = 'Not checked. Without a configured semantic verifier, results remain uncertain.';
  } catch (error) { if (!signal.aborted) status.textContent = failure(error); }
  finally { button.disabled = false; }
}
