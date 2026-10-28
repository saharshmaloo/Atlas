function webUpload(root, base, signal) {
  const form = node('form'); form.id = 'web-upload';
  const label = node('label', 'Public webpage URL'); label.htmlFor = 'web-url';
  const input = node('input'); input.type = 'url'; input.id = 'web-url'; input.required = true; input.maxLength = 2048;
  const submit = node('button', 'Save webpage', 'secondary');
  const status = node('p'); status.setAttribute('role', 'status');
  form.append(label, input, submit, status); root.append(form);
  form.onsubmit = async event => {
    event.preventDefault();
    if (submit.disabled) return;
    submit.disabled = true; status.textContent = 'Fetching webpage…';
    try {
      await api(`${base}/sources/web`, {method: 'POST', signal, headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url: input.value})});
      if (!signal.aborted) renderRoute();
    } catch (error) { if (!signal.aborted) status.textContent = failure(error); }
    finally { submit.disabled = false; }
  };
}
