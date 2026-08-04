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

async function apiGet(url) {
  const resp = await fetch(url, {
    method: 'GET',
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
      'Accept': 'application/json',
    },
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

function renderListsOptions(optionsEl, lists) {
  optionsEl.innerHTML = '';
  if (!lists.length) {
    optionsEl.innerHTML = '<p class="muted">No lists available.</p>';
    return;
  }
  lists.forEach(function (lst) {
    const label = document.createElement('label');
    if (lst.kind === 'watchlist') {
      label.classList.add('provider-listed');
    }
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.name = 'list_membership';
    input.value = lst.id;
    input.checked = !!lst.selected;
    const name = document.createElement('span');
    name.className = 'found-on-name';
    name.textContent = lst.name || lst.id;
    label.appendChild(input);
    label.appendChild(name);
    optionsEl.appendChild(label);
  });
}

function openListsDialog(opts) {
  opts = opts || {};
  const mode = opts.mode || 'membership';
  const mediaType = opts.mediaType;
  const traktId = opts.traktId;
  const title = opts.title || '';
  const presetLists = opts.lists || null;

  const modal = document.getElementById('lists-modal');
  const headingEl = document.getElementById('lists-heading');
  const titleEl = document.getElementById('lists-title');
  const hintEl = document.getElementById('lists-hint');
  const options = document.getElementById('lists-options');
  const loadingEl = document.getElementById('lists-loading');
  const errorEl = document.getElementById('lists-error');
  const saveBtn = document.getElementById('lists-save');
  const cancelBtn = document.getElementById('lists-cancel');

  if (!modal || !options || !saveBtn || !cancelBtn) {
    return Promise.resolve(null);
  }
  if (mode === 'membership' && (!mediaType || traktId === null || traktId === '')) {
    return Promise.resolve(null);
  }

  if (headingEl) {
    headingEl.textContent = mode === 'filter' ? 'Filter by lists' : 'Add to lists';
  }
  if (hintEl) {
    hintEl.textContent = mode === 'filter'
      ? 'Choose which lists to show on this page. Same lists as Preferences (Show in menu).'
      : 'Select one or more. Pre-checked from your Preferences defaults and current membership — change freely before Save.';
  }
  if (titleEl) {
    titleEl.textContent = mode === 'filter'
      ? (opts.subtitle || '')
      : (title ? ('Title: ' + title) : '');
  }
  options.innerHTML = '';
  if (errorEl) {
    errorEl.hidden = true;
    errorEl.textContent = '';
  }
  if (loadingEl) loadingEl.hidden = mode !== 'membership';
  saveBtn.disabled = mode === 'membership';
  modal.hidden = false;
  document.body.classList.add('modal-open');

  return new Promise(function (resolve) {
    let settled = false;

    function cleanup(result) {
      if (settled) return;
      settled = true;
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
      const checked = options.querySelectorAll('input[name="list_membership"]:checked');
      const selected = [];
      checked.forEach(function (el) {
        if (el.value) selected.push(el.value);
      });
      cleanup(selected);
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

    if (mode === 'filter') {
      if (loadingEl) loadingEl.hidden = true;
      renderListsOptions(options, presetLists || []);
      saveBtn.disabled = false;
      return;
    }

    apiGet('/api/lists/membership/' + mediaType + '/' + traktId)
      .then(function (data) {
        if (settled) return;
        if (loadingEl) loadingEl.hidden = true;
        renderListsOptions(options, data.lists || []);
        saveBtn.disabled = false;
      })
      .catch(function (err) {
        if (settled) return;
        if (loadingEl) loadingEl.hidden = true;
        if (errorEl) {
          errorEl.hidden = false;
          errorEl.textContent = err.message || String(err);
        }
        saveBtn.disabled = true;
      });
  });
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
  if (btn.closest('#found-on-modal') || btn.closest('#lists-modal')) return;
  ev.preventDefault();

  const action = btn.getAttribute('data-action');
  const ctx = rowContext(btn);
  const mediaType = ctx.mediaType;
  const traktId = ctx.traktId;

  if (action === 'marker-prompt-keep') {
    const el = document.getElementById('marker-prompt');
    if (el) el.hidden = true;
    return;
  }

  if (action === 'prefs-reminder') {
    const reminderAction = btn.getAttribute('data-reminder-action') || 'snooze';
    if (reminderAction === 'disable') {
      if (!window.confirm(
        'Turn off prefs reminders?\n\nWithout genres/keywords, Latest cannot filter to purple matches and will stay noisy. You can re-enable reminders under Preferences.'
      )) {
        return;
      }
    }
    btn.disabled = true;
    try {
      await apiPost('/api/prefs-reminder', { action: reminderAction });
      const banner = document.getElementById('prefs-reminder');
      if (banner) banner.hidden = true;
      if (reminderAction === 'enable') location.reload();
    } catch (err) {
      alert(err.message || String(err));
    } finally {
      btn.disabled = false;
    }
    return;
  }

  if (action === 'review-marker-clear') {
    const mt = mediaType || 'all';
    if (!window.confirm('Clear review marker for ' + mt + '?')) return;
    btn.disabled = true;
    try {
      await apiPost('/api/review-marker/' + mt + '/clear', {});
      location.reload();
    } catch (err) {
      alert(err.message || String(err));
    } finally {
      btn.disabled = false;
    }
    return;
  }

  if (action === 'review-marker-caught-up') {
    const mt = mediaType || 'all';
    if (!window.confirm(
      'Mark ' + mt + ' feed(s) as caught up as of now?\n\nThe newest title becomes the marker — everything currently listed will be dimmed.'
    )) return;
    btn.disabled = true;
    try {
      await apiPost('/api/review-marker/' + mt + '/caught-up', {});
      const el = document.getElementById('marker-prompt');
      if (el) el.hidden = true;
      alert('Markers updated to newest feed titles.');
      location.reload();
    } catch (err) {
      alert(err.message || String(err));
    } finally {
      btn.disabled = false;
    }
    return;
  }

  if (action === 'lists-filter') {
    let lists = [];
    try {
      lists = JSON.parse(btn.getAttribute('data-filter-lists') || '[]');
    } catch (err) {
      lists = [];
    }
    const currentFilter = btn.getAttribute('data-filter') || 'lists';
    btn.disabled = true;
    try {
      const selected = await openListsDialog({
        mode: 'filter',
        lists: lists,
        subtitle: btn.getAttribute('data-subtitle') || '',
      });
      if (selected === null) return;
      const params = new URLSearchParams();
      params.set('lists_set', '1');
      params.set('page', '1');
      const perPage = btn.getAttribute('data-per-page');
      if (perPage) params.set('per_page', perPage);
      // Choosing lists implies viewing those lists (not watched-only).
      params.set('filter', 'lists');
      selected.forEach(function (id) { params.append('lists', id); });
      // Keep status if user opened the menu while on Both / Unwatched.
      if (currentFilter === 'both' || currentFilter === 'unwatched_episodes') {
        params.set('filter', currentFilter);
      }
      location.search = params.toString();
    } catch (err) {
      alert(err.message || String(err));
    } finally {
      btn.disabled = false;
    }
    return;
  }

  if (!mediaType || traktId === null || traktId === '') return;

  btn.disabled = true;
  try {
    if (action === 'lists-edit' || action === 'watchlist-add' || action === 'watchlist-remove') {
      const selected = await openListsDialog({
        mode: 'membership',
        mediaType: mediaType,
        traktId: traktId,
        title: ctx.title || '',
      });
      if (selected === null) return;
      await apiPost('/api/lists/membership/' + mediaType + '/' + traktId, { selected: selected });
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
    } else if (action === 'recommendation-hide') {
      const expected = ctx.title || '';
      if (expected && !window.confirm(
        'Hide from Trakt recommendations?\n\n"' + expected + '"\n\nSame as Not interested on Trakt.tv — it will stop appearing here.'
      )) {
        return;
      }
      await apiPost('/api/recommendations/' + mediaType + '/' + traktId + '/hide', {});
      const row = btn.closest('.media-row');
      if (row) {
        row.remove();
      } else {
        location.reload();
      }
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
