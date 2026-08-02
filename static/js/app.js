/* Client helpers for CSRF-aware fetch and catalog actions. */

function csrfToken() {
  const el = document.querySelector('meta[name="csrf-token"]');
  return el ? el.getAttribute('content') : '';
}

async function apiPost(url, body) {
  body = body || {};
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
      'X-Requested-With': 'XMLHttpRequest',
    },
    body: JSON.stringify(body),
  });
  const data = await resp.json().catch(function () { return {}; });
  if (!resp.ok || data.success === false) {
    throw new Error(data.message || 'Request failed');
  }
  return data;
}

function splitPipeList(raw) {
  if (!raw) return [];
  return String(raw).split('|').map(function (s) { return s.trim(); }).filter(Boolean);
}

function namesMatch(a, b) {
  const x = String(a || '').toLowerCase();
  const y = String(b || '').toLowerCase();
  if (!x || !y) return false;
  return x === y || x.indexOf(y) !== -1 || y.indexOf(x) !== -1;
}

function openFoundOnDialog(opts) {
  opts = opts || {};
  const title = opts.title || '';
  const providers = opts.providers || [];
  const selected = opts.selected || [];

  const modal = document.getElementById('found-on-modal');
  const other = document.getElementById('found-on-other');
  const titleEl = document.getElementById('found-on-title');
  const saveBtn = document.getElementById('found-on-save');
  const cancelBtn = document.getElementById('found-on-cancel');

  if (!modal || !saveBtn || !cancelBtn) {
    const fallback = window.prompt('Found on which service? (comma-separated)', selected.join(', ') || 'Netflix');
    if (!fallback) return Promise.resolve(null);
    return Promise.resolve(
      fallback.split(',').map(function (s) { return s.trim(); }).filter(Boolean)
    );
  }

  if (titleEl) {
    titleEl.textContent = title ? ('Title: ' + title) : '';
  }
  if (other) {
    other.value = '';
  }

  const labels = modal.querySelectorAll('#found-on-options label[data-service-name]');
  labels.forEach(function (label) {
    const name = label.getAttribute('data-service-name') || '';
    const input = label.querySelector('input[type="checkbox"]');
    const listed = label.querySelector('.found-on-listed');
    const isListed = providers.some(function (p) { return namesMatch(p, name); });
    const isSelected = selected.some(function (s) { return namesMatch(s, name); });
    label.classList.toggle('provider-listed', isListed);
    if (listed) {
      listed.hidden = !isListed;
    }
    if (input) {
      input.checked = isSelected;
    }
  });

  modal.hidden = false;
  document.body.classList.add('modal-open');

  return new Promise(function (resolve) {
    function cleanup(result) {
      modal.hidden = true;
      document.body.classList.remove('modal-open');
      saveBtn.removeEventListener('click', onSave);
      cancelBtn.removeEventListener('click', onCancel);
      modal.removeEventListener('click', onBackdrop);
      document.removeEventListener('keydown', onKey);
      resolve(result);
    }

    function onSave(ev) {
      ev.preventDefault();
      ev.stopPropagation();
      const checked = modal.querySelectorAll('input[name="found_on_service"]:checked');
      const labelsOut = [];
      checked.forEach(function (el) {
        if (el.value) labelsOut.push(el.value);
      });
      const typed = other ? String(other.value || '').trim() : '';
      if (typed) labelsOut.push(typed);
      cleanup(labelsOut);
    }

    function onCancel(ev) {
      ev.preventDefault();
      ev.stopPropagation();
      cleanup(null);
    }

    function onBackdrop(ev) {
      if (ev.target === modal) cleanup(null);
    }

    function onKey(ev) {
      if (ev.key === 'Escape') cleanup(null);
    }

    saveBtn.addEventListener('click', onSave);
    cancelBtn.addEventListener('click', onCancel);
    modal.addEventListener('click', onBackdrop);
    document.addEventListener('keydown', onKey);
  });
}

function rowContext(btn) {
  const row = btn.closest('[data-trakt-id]');
  return {
    mediaType: btn.getAttribute('data-media-type') || (row && row.getAttribute('data-media-type')),
    traktId: btn.getAttribute('data-trakt-id') || (row && row.getAttribute('data-trakt-id')),
    title: btn.getAttribute('data-title') || (row && row.getAttribute('data-title')) || '',
    providers: splitPipeList(btn.getAttribute('data-providers')),
    foundOn: splitPipeList(btn.getAttribute('data-found-on')),
  };
}

document.addEventListener('click', async function (ev) {
  const btn = ev.target.closest('[data-action]');
  if (!btn) return;
  if (btn.closest('#found-on-modal')) return;
  ev.preventDefault();

  const action = btn.getAttribute('data-action');
  const ctx = rowContext(btn);
  const mediaType = ctx.mediaType;
  const traktId = ctx.traktId;
  if (!mediaType || traktId === null || traktId === '') return;

  btn.disabled = true;
  try {
    if (action === 'watchlist-add') {
      await apiPost('/api/watchlist/' + mediaType + '/' + traktId, { action: 'add' });
      location.reload();
    } else if (action === 'watchlist-remove') {
      await apiPost('/api/watchlist/' + mediaType + '/' + traktId, { action: 'remove' });
      location.reload();
    } else if (action === 'watched-add') {
      await apiPost('/api/watched/' + mediaType + '/' + traktId, { action: 'add' });
      location.reload();
    } else if (action === 'watched-remove') {
      await apiPost('/api/watched/' + mediaType + '/' + traktId, { action: 'remove' });
      location.reload();
    } else if (action === 'review-marker') {
      const expected = ctx.title || '';
      if (expected && !window.confirm(
        'Set review marker on:\n\n"' + expected + '"\n\nThat title and everything older below it will be dimmed.'
      )) {
        return;
      }
      const data = await apiPost('/api/review-marker/' + mediaType + '/' + traktId, {});
      alert('Marker set on: ' + data.title);
      location.reload();
    } else if (action === 'release-watch') {
      await apiPost('/api/release-watch/' + mediaType + '/' + traktId, {});
      btn.textContent = 'Watching release';
    } else if (action === 'found-on') {
      const labels = await openFoundOnDialog({
        title: ctx.title || '',
        providers: ctx.providers,
        selected: ctx.foundOn,
      });
      if (labels === null) return;
      await apiPost('/api/found-on/' + mediaType + '/' + traktId, { service_labels: labels });
      location.reload();
    } else if (action === 'episode-watched' || action === 'episode-unwatched') {
      const ids = JSON.parse(btn.getAttribute('data-ids') || '{}');
      await apiPost('/api/episode/watched', {
        ids: ids,
        action: action === 'episode-unwatched' ? 'remove' : 'add',
      });
      location.reload();
    } else if (action === 'sync-catalog') {
      await apiPost('/api/sync-catalog/' + mediaType, {});
      location.reload();
    }
  } catch (err) {
    alert(err.message || String(err));
  } finally {
    btn.disabled = false;
  }
});
