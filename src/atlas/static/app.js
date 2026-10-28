const $ = (id) => document.getElementById(id);
const PAGE_SIZE = 24;
let offset = 0, controller, saving = false;
const date = (value) => new Date(value).toLocaleDateString(undefined, {year:'numeric', month:'short', day:'numeric'});

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    if (response.status === 404) throw new Error('This workspace could not be found.');
    if (response.status === 422) throw new Error('Please enter a workspace name of 1–200 characters.');
    throw new Error('Atlas couldn’t complete that request. Please try again.');
  }
  return response.json();
}

function notice(message) {
  $('notice').textContent = message;
  $('notice').hidden = !message;
}

function card(workspace) {
  const link = document.createElement('a');
  link.className = 'card';
  link.href = `#/workspaces/${workspace.id}`;
  const top = document.createElement('div');
  top.className = 'card-top';
  top.setAttribute('aria-hidden', 'true');
  const folder = document.createElement('span');
  folder.className = 'folder';
  const arrow = document.createElement('span');
  arrow.textContent = '↗';
  top.append(folder, arrow);
  const title = document.createElement('h3');
  title.textContent = workspace.name;
  const time = document.createElement('time');
  time.dateTime = workspace.created_at;
  time.textContent = `Created ${date(workspace.created_at)}`;
  link.append(top, title, time);
  return link;
}

async function renderRoute() {
  controller?.abort();
  controller = new AbortController();
  const signal = controller.signal;
  $('cards').replaceChildren();
  $('library').hidden = $('detail').hidden = $('pagination').hidden = $('retry').hidden = true;
  notice('Loading your workspace…');
  const match = location.hash.match(/^#\/workspaces\/([\da-f-]+)$/i);
  const detail = Boolean(match);
  $('breadcrumb').textContent = detail ? 'YOUR INVESTIGATION' : 'YOUR LIBRARY';
  $('view-title').textContent = detail ? 'Workspace' : 'Workspaces';
  document.title = 'Workspaces · Atlas';
  try {
    if (location.hash && location.hash !== '#/' && !match) throw new Error('This page could not be found.');
    if (detail) {
      const workspace = await api(`/workspaces/${match[1]}`, {signal});
      if (signal.aborted) return;
      $('view-title').textContent = workspace.name;
      $('created').textContent = date(workspace.created_at);
      $('workspace-id').textContent = workspace.id;
      document.title = `${workspace.name} · Atlas`;
      $('detail').hidden = false;
    } else {
      const items = await api(`/workspaces?limit=${PAGE_SIZE + 1}&offset=${offset}`, {signal});
      if (signal.aborted) return;
      $('cards').replaceChildren(...items.slice(0, PAGE_SIZE).map(card));
      $('library').hidden = false;
      $('pagination').hidden = offset === 0 && items.length <= PAGE_SIZE;
      $('previous').disabled = offset === 0;
      $('next').disabled = items.length <= PAGE_SIZE;
      $('page').textContent = `Page ${offset / PAGE_SIZE + 1}`;
      if (!items.length) { notice(offset ? 'No more workspaces on this page.' : 'Your next investigation starts here. Create your first workspace.'); return; }
    }
    notice('');
  } catch (error) {
    if (signal.aborted) return;
    notice(error instanceof TypeError ? 'We couldn’t reach Atlas. Please try again.' : error.message);
    $('retry').hidden = false;
  }
}

$('skip').addEventListener('click', (event) => { event.preventDefault(); $('main').focus(); });
$('new-workspace').addEventListener('click', () => {
  $('create-form').reset();
  $('workspace-name').setCustomValidity('');
  $('form-error').hidden = true;
  $('create-dialog').showModal();
  $('workspace-name').focus();
});
$('cancel').addEventListener('click', () => $('create-dialog').close());
$('create-dialog').addEventListener('cancel', (event) => { if (saving) event.preventDefault(); });
$('workspace-name').addEventListener('input', () => $('workspace-name').setCustomValidity(''));
$('create-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const name = $('workspace-name').value.trim();
  if (!name) { $('workspace-name').setCustomValidity('Enter a workspace name.'); $('workspace-name').reportValidity(); return; }
  if (saving) return;
  saving = true;
  $('create').disabled = $('cancel').disabled = true;
  $('create').textContent = 'Creating…';
  $('form-error').hidden = true;
  try {
    const workspace = await api('/workspaces', {
      method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({name}),
    });
    $('create-dialog').close();
    offset = 0;
    location.hash = `/workspaces/${workspace.id}`;
  } catch (error) {
    $('form-error').textContent = error instanceof TypeError ? 'We couldn’t reach Atlas. Your name is still here—please try again.' : error.message;
    $('form-error').hidden = false;
  } finally {
    saving = false;
    $('create').disabled = $('cancel').disabled = false;
    $('create').textContent = 'Create workspace';
  }
});
$('previous').addEventListener('click', () => { offset = Math.max(0, offset - PAGE_SIZE); renderRoute(); });
$('next').addEventListener('click', () => { offset += PAGE_SIZE; renderRoute(); });
$('retry').addEventListener('click', renderRoute);
window.addEventListener('hashchange', () => { renderRoute(); $('view-title').focus(); });
renderRoute();
