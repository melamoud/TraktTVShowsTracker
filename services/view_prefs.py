"""
Per-user UI view settings (filters, page size) persisted on UserPreference.

Used so My / Latest / Recommendations screens restore the last choices after
navigating away. Explicit query args always win and update the saved value.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from flask import request
from flask_login import current_user

from models import UserPreference, db

logger = logging.getLogger('app')


def _ensure_prefs(user) -> UserPreference:
    prefs = getattr(user, 'preferences', None)
    if prefs is None:
        prefs = UserPreference.query.filter_by(user_id=user.id).first()
    if prefs is None:
        prefs = UserPreference(user_id=user.id)
        db.session.add(prefs)
        db.session.flush()
    return prefs


def load_all(user) -> dict:
    """Return the full view-settings map for a user."""
    prefs = _ensure_prefs(user)
    raw = getattr(prefs, 'ui_view_settings_json', None) or '{}'
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def get_view(user, view: str) -> dict:
    """Return settings dict for one view key (e.g. my_shows, latest_movies)."""
    block = load_all(user).get(view) or {}
    return block if isinstance(block, dict) else {}


def update_view(user, view: str, **updates: Any) -> None:
    """Merge updates into one view and commit."""
    if not updates:
        return
    prefs = _ensure_prefs(user)
    all_settings = load_all(user)
    block = all_settings.get(view) if isinstance(all_settings.get(view), dict) else {}
    block = dict(block)
    for key, value in updates.items():
        if value is None:
            block.pop(key, None)
        else:
            block[key] = value
    all_settings[view] = block
    prefs.ui_view_settings_json = json.dumps(all_settings)
    try:
        db.session.commit()
    except Exception as exc:
        logger.warning('Could not save view settings for %s: %s', view, exc)
        db.session.rollback()


def resolve_bool(
    user,
    view: str,
    key: str,
    arg_name: str,
    *,
    default: bool,
    true_when: str = 'not_zero',
) -> bool:
    """
    Resolve a boolean filter.

    ``true_when='not_zero'`` → present and != '0' is True (Latest hide_watched).
    ``true_when='one'`` → present and == '1' is True (on_my_services).
    """
    if arg_name in request.args:
        raw = request.args.get(arg_name)
        if true_when == 'one':
            value = raw == '1'
        else:
            value = raw != '0'
        update_view(user, view, **{key: value})
        return value
    stored = get_view(user, view).get(key)
    if isinstance(stored, bool):
        return stored
    return default


def resolve_choice(
    user,
    view: str,
    key: str,
    arg_name: str,
    *,
    allowed: set[str] | tuple[str, ...] | list[str],
    default: str,
) -> str:
    """Resolve a string choice from query args, then saved prefs, then default."""
    allowed_set = set(allowed)
    if arg_name in request.args:
        value = (request.args.get(arg_name) or '').strip().lower()
        if value in allowed_set:
            update_view(user, view, **{key: value})
            return value
    stored = get_view(user, view).get(key)
    if isinstance(stored, str) and stored in allowed_set:
        return stored
    return default


def resolve_per_page(user, view: str, *, allowed: tuple[int, ...], default: int) -> int:
    """Resolve page size from query, saved prefs, then default."""
    try:
        requested = int(request.args.get('per_page', 0) or 0)
    except (TypeError, ValueError):
        requested = 0
    if requested in allowed:
        update_view(user, view, per_page=requested)
        return requested
    stored = get_view(user, view).get('per_page')
    try:
        stored_n = int(stored)
    except (TypeError, ValueError):
        stored_n = 0
    if stored_n in allowed:
        return stored_n
    return default


def resolve_lists(
    user,
    view: str,
    shown_ids: set[str],
    *,
    defaults: list[str],
) -> list[str]:
    """
    Resolve selected list ids for My movies/shows.

    Explicit ``lists_set=1`` wins and is saved. Otherwise use saved lists for
    this view, else Preferences auto-select defaults.
    """
    if request.args.get('lists_set') == '1':
        selected = [
            str(x).strip()
            for x in request.args.getlist('lists')
            if str(x).strip() in shown_ids
        ]
        update_view(user, view, lists=selected)
        return selected

    stored = get_view(user, view).get('lists')
    if isinstance(stored, list):
        selected = [str(x) for x in stored if str(x) in shown_ids]
        # Empty saved list is intentional (user cleared all).
        return selected

    return [lid for lid in defaults if lid in shown_ids]


def current_user_or_none():
    """Return current_user when authenticated, else None."""
    try:
        if current_user and current_user.is_authenticated:
            return current_user
    except Exception:
        return None
    return None
