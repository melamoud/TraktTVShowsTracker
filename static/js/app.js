/* Client helpers for CSRF-aware fetch and catalog actions. */

function csrfToken() {
  const el = document.querySelector('meta[name="csrf-token"]');
  return el ? el.getAttribute('content') : '';
}

function userFacingError(message, fallback) {
  /** Keep alerts short; never surface SQL / stack traces in the browser. */
  const fb = fallback || 'Something went wrong. Please try again.';
  const msg = message == null ? '' : String(message).trim();
  if (!msg) return fb;
  if (
    msg.length > 180
    || /sqlalchemy|IntegrityError|OperationalError|Traceback|SQL:|UNIQUE constraint/i.test(msg)
  ) {
    return fb;
  }
  return msg;
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
    throw new Error(userFacingError(data.message, 'Request failed'));
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
    throw new Error(userFacingError(data.message, 'Request failed'));
  }
  return data;
}

let pageReloadPending = false;
let pageLoadingKeyHandler = null;

function requestReload() {
  /** Mark a reload as pending so loading feedback is not cleared before the page unloads. */
  pageReloadPending = true;
  location.reload();
}

function showPageLoading(message) {
  const overlay = document.getElementById('page-loading');
  const msg = document.getElementById('page-loading-message');
  if (msg) msg.textContent = message || 'Loading…';
  if (overlay) overlay.hidden = false;
  document.body.classList.add('page-loading-active');
  if (!pageLoadingKeyHandler) {
    pageLoadingKeyHandler = function (ev) {
      if (ev.key === 'Escape') dismissPageLoading();
    };
    document.addEventListener('keydown', pageLoadingKeyHandler);
  }
}

function hidePageLoading() {
  const overlay = document.getElementById('page-loading');
  if (overlay) overlay.hidden = true;
  document.body.classList.remove('page-loading-active');
  if (pageLoadingKeyHandler) {
    document.removeEventListener('keydown', pageLoadingKeyHandler);
    pageLoadingKeyHandler = null;
  }
}

function dismissPageLoading() {
  /** User bail-out when the overlay is stuck; does not cancel an in-flight fetch. */
  pageReloadPending = false;
  hidePageLoading();
  document.querySelectorAll('button[disabled], select[disabled]').forEach(function (el) {
    // Re-enable controls that the action handlers disabled under the overlay.
    if (el.closest('#page-loading')) return;
    el.disabled = false;
  });
}

document.addEventListener('click', function (ev) {
  const dismissBtn = ev.target.closest('#page-loading-dismiss');
  if (!dismissBtn) return;
  ev.preventDefault();
  ev.stopPropagation();
  dismissPageLoading();
});

function splitPipeList(raw) {
  if (!raw) return [];
  return String(raw).split('|').map(function (s) { return s.trim(); }).filter(Boolean);
}

function namesMatch(a, b) {
  function norm(s) {
    return String(s || '')
      .toLowerCase()
      .replace(/\+/g, ' plus ')
      .replace(/[^a-z0-9]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }
  const x = norm(a);
  const y = norm(b);
  if (!x || !y) return false;
  return x === y || x.indexOf(y) !== -1 || y.indexOf(x) !== -1;
}

function normalizeServiceName(name) {
  return String(name || '')
    .toLowerCase()
    .replace(/\+/g, ' plus ')
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function foundOnLinkMaps() {
  const el = document.getElementById('found-on-link-maps');
  if (!el) return { base_urls: {}, search_templates: {} };
  try {
    const data = JSON.parse(el.textContent || '{}');
    return {
      base_urls: data.base_urls || {},
      search_templates: data.search_templates || {},
    };
  } catch (err) {
    return { base_urls: {}, search_templates: {} };
  }
}

function applySearchTemplate(tmpl, titleText) {
  const template = String(tmpl || '').trim();
  const text = String(titleText || '').trim();
  if (!template || !text) return null;
  const encPct = encodeURIComponent(text);
  const encPlus = encodeURIComponent(text).replace(/%20/g, '+');
  const out = template
    .replace(/<title>/g, encPct)
    .replace(/\{title\}/g, encPct)
    .replace(/\{q\}/g, encPlus);
  if (out === template) return null;
  return out;
}

function foundOnOpenUrl(serviceLabel, title, year) {
  /** Mirror services.found_on_links.found_on_open_url for dialog Search links. */
  const label = String(serviceLabel || '').trim();
  if (!label) return null;
  const key = normalizeServiceName(label);
  if (key === 'cable dvr' || key === 'other' || key === 'cable' || key === 'dvr') {
    return null;
  }

  const bits = [];
  const t = String(title || '').trim();
  if (t) {
    bits.push(t);
    if (year) bits.push(String(year));
  }
  const titleText = bits.join(' ');
  const maps = foundOnLinkMaps();
  const tmpl = maps.search_templates[key];
  if (tmpl && titleText) {
    const filled = applySearchTemplate(tmpl, titleText);
    if (filled) return filled;
  }

  const base = maps.base_urls[key] || '';
  if (base && titleText) {
    let host = '';
    try {
      host = new URL(base).hostname || '';
    } catch (err) {
      host = '';
    }
    if (host) {
      return 'https://www.google.com/search?q=' + encodeURIComponent('site:' + host + ' ' + titleText);
    }
  }
  if (base) return base;
  if (titleText) {
    return 'https://www.google.com/search?q=' + encodeURIComponent(label + ' ' + titleText);
  }
  return null;
}

function renderListsOptions(optionsEl, lists, defaults) {
  optionsEl.innerHTML = '';
  if (!lists.length) {
    optionsEl.innerHTML = '<p class="muted">No lists available.</p>';
    return;
  }
  const defaultSet = {};
  (defaults || []).forEach(function (id) {
    defaultSet[String(id)] = true;
  });
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
    if (defaultSet[String(lst.id)]) {
      const mark = document.createElement('span');
      mark.className = 'muted list-default-mark';
      mark.textContent = 'default';
      label.appendChild(mark);
    }
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
  const statusEl = document.getElementById('lists-status');
  const hintEl = document.getElementById('lists-hint');
  const options = document.getElementById('lists-options');
  const loadingEl = document.getElementById('lists-loading');
  const errorEl = document.getElementById('lists-error');
  const saveBtn = document.getElementById('lists-save');
  const cancelBtn = document.getElementById('lists-cancel');
  const applyDefaultsBtn = document.getElementById('lists-apply-defaults');
  const removeAllBtn = document.getElementById('lists-remove-all');

  if (!modal || !options || !saveBtn || !cancelBtn) {
    return Promise.resolve(null);
  }
  if (mode === 'membership' && (!mediaType || traktId === null || traktId === '')) {
    return Promise.resolve(null);
  }

  if (headingEl) {
    headingEl.textContent = mode === 'filter' ? 'Filter by lists' : 'Set lists';
  }
  if (statusEl) {
    statusEl.textContent = '';
    statusEl.hidden = mode === 'filter';
  }
  if (hintEl) {
    hintEl.textContent = mode === 'filter'
      ? 'Choose which lists to show on this page. Same lists as Preferences (Show in menu).'
      : 'Toggle lists and Save to set membership for this title.';
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
  if (applyDefaultsBtn) {
    applyDefaultsBtn.hidden = mode !== 'membership';
    applyDefaultsBtn.disabled = true;
  }
  if (removeAllBtn) {
    removeAllBtn.hidden = mode !== 'membership';
    removeAllBtn.disabled = true;
  }
  modal.hidden = false;
  document.body.classList.add('modal-open');

  return new Promise(function (resolve) {
    let settled = false;
    let defaultIds = [];

    function cleanup(result) {
      if (settled) return;
      settled = true;
      modal.hidden = true;
      document.body.classList.remove('modal-open');
      saveBtn.removeEventListener('click', onSave);
      cancelBtn.removeEventListener('click', onCancel);
      if (applyDefaultsBtn) applyDefaultsBtn.removeEventListener('click', onApplyDefaults);
      if (removeAllBtn) removeAllBtn.removeEventListener('click', onRemoveAll);
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

    function onApplyDefaults(ev) {
      ev.preventDefault();
      ev.stopPropagation();
      options.querySelectorAll('input[name="list_membership"]').forEach(function (el) {
        if (defaultIds.indexOf(el.value) !== -1) {
          el.checked = true;
        }
      });
    }

    function onRemoveAll(ev) {
      ev.preventDefault();
      ev.stopPropagation();
      if (!window.confirm('Remove this title from all lists shown here?')) return;
      cleanup([]);
    }

    function onBackdrop(ev) {
      if (ev.target === modal) cleanup(null);
    }

    function onKey(ev) {
      if (ev.key === 'Escape') cleanup(null);
    }

    saveBtn.addEventListener('click', onSave);
    cancelBtn.addEventListener('click', onCancel);
    if (applyDefaultsBtn) applyDefaultsBtn.addEventListener('click', onApplyDefaults);
    if (removeAllBtn) removeAllBtn.addEventListener('click', onRemoveAll);
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
        defaultIds = (data.defaults || []).map(String);
        const lists = data.lists || [];
        renderListsOptions(options, lists, defaultIds);
        const onNames = lists.filter(function (lst) { return lst.on_list; })
          .map(function (lst) { return lst.name || lst.id; });
        if (statusEl) {
          statusEl.hidden = false;
          statusEl.textContent = onNames.length
            ? ('Currently on: ' + onNames.join(', '))
            : 'Not on any list yet';
        }
        if (hintEl) {
          hintEl.textContent = onNames.length
            ? 'Toggle lists and Save to update membership. Use Remove from all lists to clear everything.'
            : 'Not on any list — check lists or Apply my defaults, then Save.';
        }
        if (applyDefaultsBtn) applyDefaultsBtn.disabled = false;
        if (removeAllBtn) removeAllBtn.disabled = !onNames.length;
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
        if (applyDefaultsBtn) applyDefaultsBtn.disabled = true;
        if (removeAllBtn) removeAllBtn.disabled = true;
      });
  });
}

function openFoundOnDialog(opts) {
  opts = opts || {};
  const title = opts.title || '';
  const year = opts.year || null;
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

  const rows = modal.querySelectorAll('#found-on-options .found-on-option[data-service-name]');
  rows.forEach(function (row) {
    const name = row.getAttribute('data-service-name') || '';
    const input = row.querySelector('input[type="checkbox"]');
    const listed = row.querySelector('.found-on-listed');
    const searchLink = row.querySelector('.found-on-search');
    const isListed = providers.some(function (p) { return namesMatch(p, name); });
    const isSelected = selected.some(function (s) { return namesMatch(s, name); });
    row.classList.toggle('provider-listed', isListed);
    if (listed) {
      listed.hidden = !isListed;
    }
    if (input) {
      input.checked = isSelected;
    }
    if (searchLink) {
      const href = foundOnOpenUrl(name, title, year);
      if (href) {
        searchLink.href = href;
        searchLink.hidden = false;
      } else {
        searchLink.removeAttribute('href');
        searchLink.hidden = true;
      }
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

function openReviewDialog(opts) {
  opts = opts || {};
  const mode = opts.mode || 'review'; // 'review' | 'episode'
  const title = opts.title || '';
  const mediaType = opts.mediaType || (mode === 'episode' ? 'episode' : null);
  const traktId = opts.traktId || null;
  const alreadyWatched = !!opts.watched;
  const modal = document.getElementById('review-modal');
  const headingEl = document.getElementById('review-heading');
  const titleEl = document.getElementById('review-title');
  const hintEl = document.getElementById('review-hint');
  const loadingEl = document.getElementById('review-loading');
  const ratingWrap = document.getElementById('review-rating-wrap');
  const ratingEl = document.getElementById('review-rating');
  const textEl = document.getElementById('review-text');
  const spoilerEl = document.getElementById('review-spoiler');
  const watchWrap = document.getElementById('review-watch-wrap');
  const watchBtn = document.getElementById('review-watch-btn');
  const watchHint = document.getElementById('review-watch-hint');
  const errorEl = document.getElementById('review-error');
  const saveBtn = document.getElementById('review-save');
  const cancelBtn = document.getElementById('review-cancel');

  if (!modal || !textEl || !saveBtn || !cancelBtn) {
    const fallback = window.prompt('Write a Trakt review (at least 5 words):', '');
    if (!fallback) return Promise.resolve(null);
    return Promise.resolve({
      comment: fallback.trim(),
      spoiler: false,
      rating: null,
      ratingAction: null,
      commentId: null,
      markWatched: false,
    });
  }

  const isEpisode = mode === 'episode';
  let initialRating = null;
  let initialComment = '';
  let initialSpoiler = false;
  let commentId = null;

  if (headingEl) {
    headingEl.textContent = isEpisode ? 'Rate / Review episode' : 'Write a review';
  }
  if (hintEl) {
    hintEl.textContent = isEpisode
      ? 'Loaded from Trakt when available. Change rating, review, and/or mark watched — then Save once.'
      : 'Loads your existing Trakt comment when available. Use at least 5 words.';
  }
  if (titleEl) {
    titleEl.textContent = title ? ('About: ' + title) : '';
  }
  if (ratingWrap) ratingWrap.hidden = !isEpisode;
  if (watchWrap) watchWrap.hidden = !isEpisode;
  if (ratingEl) {
    // Hide Clear until we know there is an existing rating.
    const clearOpt = ratingEl.querySelector('option[value="clear"]');
    if (clearOpt) clearOpt.hidden = true;
    ratingEl.value = '';
  }
  textEl.value = '';
  if (spoilerEl) spoilerEl.checked = false;
  if (errorEl) {
    errorEl.hidden = true;
    errorEl.textContent = '';
  }
  if (loadingEl) loadingEl.hidden = true;
  saveBtn.disabled = false;

  let markWatched = false;
  function syncWatchBtn() {
    if (!watchBtn) return;
    if (alreadyWatched) {
      markWatched = false;
      watchBtn.disabled = true;
      watchBtn.setAttribute('aria-pressed', 'false');
      watchBtn.classList.remove('btn-primary');
      watchBtn.textContent = 'Already watched';
      if (watchHint) watchHint.textContent = 'This episode is already in your Trakt history.';
      return;
    }
    watchBtn.disabled = false;
    watchBtn.setAttribute('aria-pressed', markWatched ? 'true' : 'false');
    watchBtn.classList.toggle('btn-primary', markWatched);
    watchBtn.textContent = markWatched ? 'Will mark watched' : 'Mark watched';
    if (watchHint) {
      watchHint.textContent = markWatched
        ? 'Save will also add this episode to watch history.'
        : 'Optional — include a watch mark when you save.';
    }
  }
  syncWatchBtn();

  if (saveBtn) {
    saveBtn.textContent = isEpisode ? 'Save to Trakt' : 'Post to Trakt';
  }

  function applyFeedback(data) {
    data = data || {};
    initialRating = data.rating != null ? Number(data.rating) : null;
    initialComment = String(data.comment || '');
    initialSpoiler = !!data.spoiler;
    commentId = data.comment_id || null;
    if (ratingEl && isEpisode) {
      const clearOpt = ratingEl.querySelector('option[value="clear"]');
      if (clearOpt) clearOpt.hidden = !initialRating;
      ratingEl.value = initialRating ? String(initialRating) : '';
    }
    textEl.value = initialComment;
    if (spoilerEl) spoilerEl.checked = initialSpoiler;
  }

  modal.hidden = false;
  document.body.classList.add('modal-open');

  const loadPromise = (mediaType && traktId)
    ? (async function () {
      if (loadingEl) loadingEl.hidden = false;
      saveBtn.disabled = true;
      try {
        const data = await apiGet('/api/feedback/' + mediaType + '/' + traktId);
        applyFeedback(data);
      } catch (err) {
        if (errorEl) {
          errorEl.textContent = err.message || 'Could not load existing Trakt data.';
          errorEl.hidden = false;
        }
      } finally {
        if (loadingEl) loadingEl.hidden = true;
        saveBtn.disabled = false;
        if (isEpisode && ratingEl) ratingEl.focus();
        else textEl.focus();
      }
    })()
    : Promise.resolve().then(function () {
      if (isEpisode && ratingEl) ratingEl.focus();
      else textEl.focus();
    });

  return new Promise(function (resolve) {
    function cleanup(result) {
      modal.hidden = true;
      document.body.classList.remove('modal-open');
      saveBtn.removeEventListener('click', onSave);
      cancelBtn.removeEventListener('click', onCancel);
      if (watchBtn) watchBtn.removeEventListener('click', onWatchToggle);
      modal.removeEventListener('click', onBackdrop);
      document.removeEventListener('keydown', onKey);
      resolve(result);
    }

    function showError(msg) {
      if (!errorEl) {
        alert(msg);
        return;
      }
      errorEl.textContent = msg;
      errorEl.hidden = false;
    }

    function onWatchToggle(ev) {
      ev.preventDefault();
      ev.stopPropagation();
      if (alreadyWatched) return;
      markWatched = !markWatched;
      syncWatchBtn();
    }

    function onSave(ev) {
      ev.preventDefault();
      ev.stopPropagation();
      const comment = String(textEl.value || '').trim();
      const words = comment.split(/\s+/).filter(Boolean);
      const ratingRaw = ratingEl ? String(ratingEl.value || '') : '';
      let rating = null;
      let ratingAction = null; // 'set' | 'clear' | null
      if (isEpisode) {
        if (ratingRaw === 'clear') {
          if (initialRating) ratingAction = 'clear';
        } else if (ratingRaw) {
          rating = Number(ratingRaw);
          if (rating !== initialRating) ratingAction = 'set';
        }
      }

      const spoilerOn = !!(spoilerEl && spoilerEl.checked);
      const commentChanged = comment !== initialComment || spoilerOn !== initialSpoiler;
      const shouldWriteComment = !!comment && (commentChanged || (!commentId && comment));

      if (comment && words.length < 5) {
        showError(isEpisode
          ? 'Reviews need at least 5 words (or clear the text).'
          : 'Trakt needs at least 5 words.');
        return;
      }

      if (isEpisode) {
        if (!ratingAction && !shouldWriteComment && !markWatched) {
          showError('Change the rating, edit the review, or mark watched.');
          return;
        }
      } else if (!shouldWriteComment) {
        showError('Trakt needs at least 5 words.');
        return;
      }

      cleanup({
        comment: shouldWriteComment ? comment : null,
        spoiler: spoilerOn,
        commentId: commentId,
        rating: rating,
        ratingAction: ratingAction,
        markWatched: isEpisode && markWatched && !alreadyWatched,
      });
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
    if (watchBtn) watchBtn.addEventListener('click', onWatchToggle);
    modal.addEventListener('click', onBackdrop);
    document.addEventListener('keydown', onKey);

    // Keep handlers active while feedback loads; user can cancel anytime.
    loadPromise.catch(function () { /* errors surfaced in dialog */ });
  });
}

function rowContext(btn) {
  const row = btn.closest('[data-trakt-id]');
  const yearRaw = btn.getAttribute('data-year') || (row && row.getAttribute('data-year')) || '';
  const yearNum = parseInt(yearRaw, 10);
  return {
    mediaType: btn.getAttribute('data-media-type') || (row && row.getAttribute('data-media-type')),
    traktId: btn.getAttribute('data-trakt-id') || (row && row.getAttribute('data-trakt-id')),
    title: btn.getAttribute('data-title') || (row && row.getAttribute('data-title')) || '',
    year: Number.isFinite(yearNum) ? yearNum : null,
    providers: splitPipeList(btn.getAttribute('data-providers')),
    foundOn: splitPipeList(btn.getAttribute('data-found-on')),
  };
}

let progressDrawerTraktId = null;
let progressDrawerDirty = false;
let progressDrawerKeyHandler = null;

function isProgressDrawerOpen() {
  const drawer = document.getElementById('progress-drawer');
  return !!(drawer && !drawer.hidden);
}

function closeProgressDrawer() {
  const drawer = document.getElementById('progress-drawer');
  if (!drawer) return;
  drawer.hidden = true;
  document.body.classList.remove('modal-open');
  if (progressDrawerKeyHandler) {
    document.removeEventListener('keydown', progressDrawerKeyHandler);
    progressDrawerKeyHandler = null;
  }
  const dirty = progressDrawerDirty;
  progressDrawerDirty = false;
  progressDrawerTraktId = null;
  if (dirty) {
    requestReload();
  }
}

async function refreshProgressDrawer() {
  const body = document.getElementById('progress-drawer-body');
  const loadingEl = document.getElementById('progress-drawer-loading');
  const errorEl = document.getElementById('progress-drawer-error');
  if (!body || !progressDrawerTraktId) return;
  if (loadingEl) loadingEl.hidden = false;
  if (errorEl) {
    errorEl.hidden = true;
    errorEl.textContent = '';
  }
  try {
    const resp = await fetch(
      '/shows/' + progressDrawerTraktId + '/progress?partial=1',
      {
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          'Accept': 'text/html',
        },
      }
    );
    const html = await resp.text();
    if (!resp.ok) {
      throw new Error(html.replace(/<[^>]+>/g, '').trim() || 'Failed to load progress');
    }
    body.innerHTML = html;
  } catch (err) {
    if (errorEl) {
      errorEl.hidden = false;
      errorEl.textContent = err.message || String(err);
    }
  } finally {
    if (loadingEl) loadingEl.hidden = true;
  }
}

async function openProgressDrawer(opts) {
  opts = opts || {};
  const traktId = opts.traktId;
  const title = opts.title || '';
  const drawer = document.getElementById('progress-drawer');
  const titleEl = document.getElementById('progress-drawer-title');
  const body = document.getElementById('progress-drawer-body');
  const closeBtn = document.getElementById('progress-drawer-close');
  const errorEl = document.getElementById('progress-drawer-error');
  if (!drawer || !body || !traktId) return;

  progressDrawerTraktId = String(traktId);
  progressDrawerDirty = false;
  if (titleEl) titleEl.textContent = title || ('Show ' + traktId);
  body.innerHTML = '';
  if (errorEl) {
    errorEl.hidden = true;
    errorEl.textContent = '';
  }
  drawer.hidden = false;
  document.body.classList.add('modal-open');

  function onKey(ev) {
    if (ev.key === 'Escape') closeProgressDrawer();
  }
  progressDrawerKeyHandler = onKey;
  document.addEventListener('keydown', onKey);

  if (closeBtn && !closeBtn._progressBound) {
    closeBtn.addEventListener('click', function (ev) {
      ev.preventDefault();
      closeProgressDrawer();
    });
    closeBtn._progressBound = true;
  }
  if (!drawer._progressBound) {
    drawer.addEventListener('click', function (ev) {
      if (ev.target === drawer) closeProgressDrawer();
    });
    drawer._progressBound = true;
  }

  await refreshProgressDrawer();
}

async function afterProgressMutation() {
  if (isProgressDrawerOpen() && progressDrawerTraktId) {
    progressDrawerDirty = true;
    await refreshProgressDrawer();
    return;
  }
  requestReload();
}

document.addEventListener('change', async function (ev) {
  const el = ev.target.closest('select.rate-select');
  if (!el) return;
  const mediaType = el.getAttribute('data-media-type');
  const traktId = el.getAttribute('data-trakt-id');
  if (!mediaType || !traktId) return;
  const value = el.value;
  if (value === '') return;
  el.disabled = true;
  showPageLoading('Saving rating…');
  try {
    const rating = value === 'clear' ? null : Number(value);
    await apiPost('/api/rating/' + mediaType + '/' + traktId, { rating: rating });
    requestReload();
  } catch (err) {
    alert(err.message || String(err));
    el.disabled = false;
    hidePageLoading();
  }
});

/* Global loading feedback for page leaves/reloads and refresh links. */
window.addEventListener('beforeunload', function () {
  const overlay = document.getElementById('page-loading');
  if (overlay && overlay.hidden) {
    showPageLoading('Loading page…');
  }
});

document.addEventListener('submit', function (ev) {
  const form = ev.target.closest('form');
  if (!form) return;
  const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
  if (submitBtn) submitBtn.disabled = true;
  showPageLoading('Submitting…');
  // If an inline handler cancels the submit, hide the overlay and re-enable the button.
  setTimeout(function () {
    if (ev.defaultPrevented) {
      hidePageLoading();
      if (submitBtn) submitBtn.disabled = false;
    }
  }, 0);
});

document.addEventListener('click', function (ev) {
  const link = ev.target.closest('a[data-loading], a[href*="refresh=1"], a[href*="load_older=1"]');
  if (!link) return;
  showPageLoading(link.getAttribute('data-loading-message') || 'Refreshing…');
});

document.addEventListener('click', async function (ev) {
  const btn = ev.target.closest('[data-action]');
  if (!btn) return;
  if (btn.closest('#found-on-modal') || btn.closest('#lists-modal') || btn.closest('#review-modal')) return;
  ev.preventDefault();

  const action = btn.getAttribute('data-action');
  const ctx = rowContext(btn);
  const mediaType = ctx.mediaType;
  const traktId = ctx.traktId;

  // Show the global loading overlay for immediate server actions only.
  // Dialogs / confirms / drawers must not sit under the overlay (it is above modals).
  const noOverlayActions = [
    'marker-prompt-keep',
    'lists-filter',
    'lists-edit',
    'watchlist-add',
    'watchlist-remove',
    'progress-open',
    'review-add',
    'episode-rate-review',
    'found-on',
    'prefs-reminder',
    'review-marker-clear',
    'review-marker-caught-up',
    'watched-add',
    'watched-remove',
    'review-marker',
    'recommendation-hide',
    'season-watched',
    'season-unwatched',
    'series-watched',
  ];
  if (!noOverlayActions.includes(action)) {
    showPageLoading(btn.getAttribute('data-loading-message') || 'Working…');
  }

  if (action === 'marker-prompt-keep') {
    const el = document.getElementById('marker-prompt');
    if (el) el.hidden = true;
    return;
  }

  if (action === 'episode-rate-review') {
    const id = traktId || btn.getAttribute('data-trakt-id');
    if (!id) return;
    let ids = {};
    try {
      ids = JSON.parse(btn.getAttribute('data-ids') || '{}');
    } catch (err) {
      ids = {};
    }
    const watched = btn.getAttribute('data-watched') === '1';
    btn.disabled = true;
    try {
      const draft = await openReviewDialog({
        mode: 'episode',
        mediaType: 'episode',
        traktId: id,
        title: ctx.title || btn.getAttribute('data-title') || '',
        watched: watched,
      });
      if (!draft) return;
      showPageLoading('Saving to Trakt…');
      const jobs = [];
      if (draft.ratingAction === 'set') {
        jobs.push(apiPost('/api/rating/episode/' + id, { rating: draft.rating }));
      } else if (draft.ratingAction === 'clear') {
        jobs.push(apiPost('/api/rating/episode/' + id, { rating: null }));
      }
      if (draft.comment) {
        const body = { comment: draft.comment, spoiler: draft.spoiler };
        if (draft.commentId) body.comment_id = draft.commentId;
        jobs.push(apiPost('/api/comment/episode/' + id, body));
      }
      if (draft.markWatched) {
        jobs.push(apiPost('/api/episode/watched', { ids: ids, action: 'add' }));
      }
      await Promise.all(jobs);
      await afterProgressMutation();
    } catch (err) {
      alert(err.message || String(err));
    } finally {
      btn.disabled = false;
      hidePageLoading();
    }
    return;
  }

  if (action === 'review-add') {
    const id = traktId || btn.getAttribute('data-trakt-id');
    const type = mediaType || btn.getAttribute('data-media-type');
    if (!id || !type) return;
    btn.disabled = true;
    try {
      const draft = await openReviewDialog({
        mode: 'review',
        mediaType: type,
        traktId: id,
        title: ctx.title || btn.getAttribute('data-title') || '',
      });
      if (!draft || !draft.comment) return;
      showPageLoading('Saving review…');
      const body = { comment: draft.comment, spoiler: draft.spoiler };
      if (draft.commentId) body.comment_id = draft.commentId;
      const data = await apiPost('/api/comment/' + type + '/' + id, body);
      const kind = data.review ? 'Review' : 'Comment';
      alert(kind + ' saved on Trakt.');
    } catch (err) {
      alert(err.message || String(err));
    } finally {
      btn.disabled = false;
      hidePageLoading();
    }
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
    showPageLoading('Saving…');
    try {
      await apiPost('/api/prefs-reminder', { action: reminderAction });
      const banner = document.getElementById('prefs-reminder');
      if (banner) banner.hidden = true;
      if (reminderAction === 'enable') requestReload();
    } catch (err) {
      alert(err.message || String(err));
    } finally {
      if (!pageReloadPending) {
        btn.disabled = false;
        hidePageLoading();
      }
    }
    return;
  }

  if (action === 'review-marker-clear') {
    const mt = mediaType || 'all';
    if (!window.confirm('Clear review marker for ' + mt + '?')) return;
    btn.disabled = true;
    showPageLoading('Clearing marker…');
    try {
      await apiPost('/api/review-marker/' + mt + '/clear', {});
      requestReload();
    } catch (err) {
      alert(err.message || String(err));
    } finally {
      if (!pageReloadPending) {
        btn.disabled = false;
        hidePageLoading();
      }
    }
    return;
  }

  if (action === 'review-marker-caught-up') {
    const mt = mediaType || 'all';
    if (!window.confirm(
      'Mark ' + mt + ' feed(s) as caught up as of now?\n\nThe newest title becomes the marker — everything currently listed will be dimmed.'
    )) return;
    btn.disabled = true;
    showPageLoading('Updating markers…');
    try {
      await apiPost('/api/review-marker/' + mt + '/caught-up', {});
      const el = document.getElementById('marker-prompt');
      if (el) el.hidden = true;
      alert('Markers updated to newest feed titles.');
      requestReload();
    } catch (err) {
      alert(err.message || String(err));
    } finally {
      if (!pageReloadPending) {
        btn.disabled = false;
        hidePageLoading();
      }
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
      if (
        currentFilter === 'both'
        || currentFilter === 'unwatched'
        || currentFilter === 'unwatched_episodes'
      ) {
        params.set('filter', currentFilter);
      }
      pageReloadPending = true;
      showPageLoading('Loading page…');
      location.search = params.toString();
    } catch (err) {
      alert(err.message || String(err));
    } finally {
      if (!pageReloadPending) {
        btn.disabled = false;
      }
    }
    return;
  }

  if (action === 'progress-open') {
    const id = traktId || btn.getAttribute('data-trakt-id');
    if (!id) return;
    btn.disabled = true;
    try {
      await openProgressDrawer({
        traktId: id,
        title: ctx.title || btn.getAttribute('data-title') || '',
      });
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
      // null = Cancel. [] = clear all lists (remove from Wishlist + personal lists).
      if (selected === null) return;
      showPageLoading('Saving lists…');
      await apiPost('/api/lists/membership/' + mediaType + '/' + traktId, {
        selected: Array.isArray(selected) ? selected : [],
      });
      requestReload();
    } else if (action === 'pin-add' || action === 'pin-remove') {
      await apiPost('/api/pin/' + mediaType + '/' + traktId, {
        action: action === 'pin-remove' ? 'unpin' : 'pin',
      });
      requestReload();
    } else if (action === 'favorite-add' || action === 'favorite-remove') {
      await apiPost('/api/favorite/' + mediaType + '/' + traktId, {
        action: action === 'favorite-remove' ? 'remove' : 'add',
      });
      requestReload();
    } else if (action === 'favorite-actor-add' || action === 'favorite-actor-remove') {
      showPageLoading(action === 'favorite-actor-remove' ? 'Updating…' : 'Saving favorite actor…');
      await apiPost('/api/favorite-actor/' + traktId, {
        action: action === 'favorite-actor-remove' ? 'remove' : 'add',
      });
      requestReload();
    } else if (action === 'watched-add') {
      const label = ctx.title || 'this title';
      const warn = mediaType === 'show'
        ? 'Mark ALL aired seasons/episodes of "' + label + '" as watched on Trakt?\n\n'
          + 'This writes every remaining episode into watch history (not just the season you meant).'
        : 'Mark "' + label + '" as watched on Trakt?';
      if (!window.confirm(warn)) {
        return;
      }
      showPageLoading('Marking watched…');
      await apiPost('/api/watched/' + mediaType + '/' + traktId, { action: 'add' });
      requestReload();
    } else if (action === 'watched-remove') {
      const label = ctx.title || 'this title';
      const warn = mediaType === 'show'
        ? 'Remove ALL watch history for "' + label + '" on Trakt?\n\n'
          + 'Every season/episode play for this show will be cleared.'
        : 'Remove "' + label + '" from Trakt watch history?';
      if (!window.confirm(warn)) {
        return;
      }
      showPageLoading('Removing watch…');
      await apiPost('/api/watched/' + mediaType + '/' + traktId, { action: 'remove' });
      requestReload();
    } else if (action === 'review-marker') {
      const expected = ctx.title || '';
      if (expected && !window.confirm(
        'Set review marker on:\n\n"' + expected + '"\n\nThat title and everything older below it will be dimmed.'
      )) {
        return;
      }
      showPageLoading('Setting marker…');
      const data = await apiPost('/api/review-marker/' + mediaType + '/' + traktId, {});
      alert('Marker set on: ' + data.title);
      requestReload();
    } else if (action === 'recommendation-hide') {
      const expected = ctx.title || '';
      if (expected && !window.confirm(
        'Hide from Trakt recommendations?\n\n"' + expected + '"\n\nSame as Not interested on Trakt.tv — it will stop appearing here.'
      )) {
        return;
      }
      showPageLoading('Hiding…');
      await apiPost('/api/recommendations/' + mediaType + '/' + traktId + '/hide', {});
      const row = btn.closest('.media-row');
      if (row) {
        row.remove();
      } else {
        requestReload();
      }
    } else if (action === 'found-on') {
      const labels = await openFoundOnDialog({
        title: ctx.title || '',
        year: ctx.year,
        providers: ctx.providers,
        selected: ctx.foundOn,
      });
      if (labels === null) return;
      showPageLoading('Saving…');
      await apiPost('/api/found-on/' + mediaType + '/' + traktId, { service_labels: labels });
      requestReload();
    } else if (action === 'episode-watched' || action === 'episode-unwatched') {
      const ids = JSON.parse(btn.getAttribute('data-ids') || '{}');
      await apiPost('/api/episode/watched', {
        ids: ids,
        action: action === 'episode-unwatched' ? 'remove' : 'add',
      });
      await afterProgressMutation();
    } else if (action === 'season-watched') {
      const season = btn.getAttribute('data-season');
      const label = ctx.title || ('Season ' + season);
      if (!window.confirm(
        'Mark all aired episodes in ' + label + ' as watched on Trakt?'
      )) {
        return;
      }
      showPageLoading('Marking season watched…');
      await apiPost('/api/show/' + traktId + '/season/' + season + '/watched', {});
      await afterProgressMutation();
    } else if (action === 'season-unwatched') {
      const season = btn.getAttribute('data-season');
      const label = ctx.title || ('Season ' + season);
      if (!window.confirm(
        'Remove all watch history for ' + label + ' on Trakt?\n\n'
        + 'Only this season is cleared — other seasons stay as they are.'
      )) {
        return;
      }
      showPageLoading('Unwatching season…');
      await apiPost('/api/show/' + traktId + '/season/' + season + '/unwatched', {});
      await afterProgressMutation();
    } else if (action === 'series-watched') {
      const expected = ctx.title || 'this show';
      if (!window.confirm(
        'Mark ALL aired seasons/episodes of "' + expected + '" as watched on Trakt?\n\n'
        + 'This writes every remaining episode into watch history.'
      )) {
        return;
      }
      showPageLoading('Marking series watched…');
      await apiPost('/api/watched/show/' + traktId, { action: 'add' });
      await afterProgressMutation();
    } else if (action === 'sync-catalog') {
      await apiPost('/api/sync-catalog/' + mediaType, {});
      requestReload();
    }
  } catch (err) {
    alert(err.message || String(err));
  } finally {
    if (!pageReloadPending) {
      btn.disabled = false;
      hidePageLoading();
    }
  }
});
