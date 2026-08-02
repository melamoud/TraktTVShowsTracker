"""
Admin privilege bootstrap from configured Trakt usernames.
"""

from flask import current_app

from models import AppMeta, User, db


def admin_already_bootstrapped() -> bool:
    """True when at least one admin user exists or bootstrap lock is set."""
    if User.query.filter_by(is_admin=True).first():
        return True
    meta = db.session.get(AppMeta, 'admin_bootstrapped')
    return bool(meta and meta.value == '1')


def mark_admin_bootstrapped() -> None:
    """Persist bootstrap completion flag."""
    meta = db.session.get(AppMeta, 'admin_bootstrapped')
    if not meta:
        meta = AppMeta(key='admin_bootstrapped', value='1')
        db.session.add(meta)
    else:
        meta.value = '1'
    db.session.commit()


def maybe_grant_admin(user: User) -> bool:
    """
    Grant admin if username is listed in ADMIN_TRAKT_USERNAMES and policy allows.

    Safest default: after one admin exists, env list cannot promote others
    unless ADMIN_ALLOW_ENV_PROMOTE=1.
    Returns True if user is admin after this call.
    """
    usernames = [u.lower() for u in current_app.config.get('ADMIN_TRAKT_USERNAMES') or []]
    allow_env = current_app.config.get('ADMIN_ALLOW_ENV_PROMOTE', False)
    candidate = (user.username or '').lower()

    if user.is_admin:
        return True

    if candidate not in usernames:
        return False

    if admin_already_bootstrapped() and not allow_env:
        current_app.logger.info(
            'Admin env promote skipped for %s (bootstrap already done)', user.username
        )
        return False

    user.is_admin = True
    db.session.commit()
    mark_admin_bootstrapped()
    current_app.logger.info('Granted admin to Trakt user %s', user.username)
    return True
