"""
Google Calendar OAuth and event writes.

Uses the Calendar API over ``requests`` (no Google client library). Tokens are
stored encrypted on ``UserGoogleCalendar``. The user picks the Google account
on Google's screen, then picks one writable calendar in Preferences.
"""

from __future__ import annotations

import logging
import secrets
import time
from datetime import datetime, timedelta
from urllib.parse import quote, urlencode

import requests
from flask import current_app

from models import GoogleOAuthState, UserGoogleCalendar, db
from services.crypto_tokens import decrypt_token, encrypt_token

logger = logging.getLogger('app')

AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
USERINFO_URL = 'https://www.googleapis.com/oauth2/v2/userinfo'
CALENDAR_API = 'https://www.googleapis.com/calendar/v3'
SCOPES = ' '.join([
    'openid',
    'email',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/calendar.calendarlist.readonly',
    'https://www.googleapis.com/auth/calendar.events',
])


class GoogleCalendarError(Exception):
    """Google OAuth or Calendar API failure the UI can show."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def google_configured() -> bool:
    """True when the server has a Google OAuth client id and secret."""
    client_id = (current_app.config.get('GOOGLE_CLIENT_ID') or '').strip()
    secret = (current_app.config.get('GOOGLE_CLIENT_SECRET') or '').strip()
    return bool(client_id and secret)


def _redirect_uri() -> str:
    return (current_app.config.get('GOOGLE_CALENDAR_REDIRECT_URI') or '').strip()


def _client_id() -> str:
    return (current_app.config.get('GOOGLE_CLIENT_ID') or '').strip()


def _client_secret() -> str:
    return (current_app.config.get('GOOGLE_CLIENT_SECRET') or '').strip()


def _token_request(data: dict) -> dict:
    try:
        resp = requests.post(TOKEN_URL, data=data, timeout=20)
    except requests.RequestException as exc:
        raise GoogleCalendarError('Could not reach Google.') from exc
    if resp.status_code != 200:
        raise GoogleCalendarError('Google token request failed.', status_code=resp.status_code)
    payload = resp.json()
    if not isinstance(payload, dict):
        raise GoogleCalendarError('Google returned an unexpected token response.')
    return payload


def _expires_at(payload: dict) -> datetime:
    seconds = int(payload.get('expires_in') or 3600) - 60
    return datetime.utcnow() + timedelta(seconds=max(seconds, 30))


def exchange_code(code: str) -> dict:
    """Trade an authorization code for access and refresh tokens."""
    if not code:
        raise GoogleCalendarError('Missing authorization code from Google.')
    return _token_request({
        'code': code,
        'client_id': _client_id(),
        'client_secret': _client_secret(),
        'redirect_uri': _redirect_uri(),
        'grant_type': 'authorization_code',
    })


def fetch_email(access_token: str) -> str:
    """Return the Google account email for an access token."""
    try:
        resp = requests.get(
            USERINFO_URL,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=20,
        )
    except requests.RequestException as exc:
        raise GoogleCalendarError('Could not read the Google account email.') from exc
    if resp.status_code != 200:
        raise GoogleCalendarError('Could not read the Google account email.', status_code=resp.status_code)
    email = (resp.json() or {}).get('email') or ''
    return str(email).strip() or 'Google account'


def authorize_url(state: str) -> str:
    """Google account-chooser URL. ``prompt`` lets the user pick the account."""
    query = urlencode({
        'client_id': _client_id(),
        'redirect_uri': _redirect_uri(),
        'response_type': 'code',
        'scope': SCOPES,
        'access_type': 'offline',
        'prompt': 'select_account consent',
        'state': state,
        'include_granted_scopes': 'true',
    })
    return f'{AUTH_URL}?{query}'


def begin_oauth(user_id: int, client_kind: str) -> str:
    """Store a one-time state and return the Google authorize URL."""
    if not google_configured():
        raise GoogleCalendarError(
            'Google Calendar is not configured on this server yet.'
        )
    if not _redirect_uri():
        raise GoogleCalendarError('GOOGLE_CALENDAR_REDIRECT_URI is not set.')
    now = datetime.utcnow()
    GoogleOAuthState.query.filter(GoogleOAuthState.expires_at < now).delete(
        synchronize_session=False,
    )
    GoogleOAuthState.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    state = secrets.token_urlsafe(24)
    db.session.add(GoogleOAuthState(
        state=state,
        user_id=user_id,
        client_kind=client_kind if client_kind in ('web', 'android') else 'web',
        expires_at=now + timedelta(minutes=15),
    ))
    db.session.commit()
    return authorize_url(state)


def complete_oauth(state: str, code: str) -> tuple:
    """
    Finish Google sign-in.

    Returns ``(user, client_kind)``. Raises ``GoogleCalendarError`` on failure.
    """
    from models import User

    row = GoogleOAuthState.query.filter_by(state=(state or '').strip()).first()
    if not row or not row.expires_at or row.expires_at < datetime.utcnow():
        raise GoogleCalendarError('Google sign-in expired. Connect again from Preferences.')
    user = db.session.get(User, row.user_id)
    kind = row.client_kind or 'web'
    if not user:
        db.session.delete(row)
        db.session.commit()
        raise GoogleCalendarError('That sign-in is no longer linked to an account.')
    db.session.delete(row)
    db.session.commit()

    tokens = exchange_code(code)
    access = tokens.get('access_token')
    if not access:
        raise GoogleCalendarError('Google did not return an access token.')
    email = fetch_email(access)
    link = UserGoogleCalendar.query.filter_by(user_id=user.id).first()
    if not link:
        link = UserGoogleCalendar(user_id=user.id, connected_at=datetime.utcnow())
        db.session.add(link)
    link.account_email = email
    link.access_token_enc = encrypt_token(access)
    refresh = tokens.get('refresh_token')
    if refresh:
        link.refresh_token_enc = encrypt_token(refresh)
    elif not link.refresh_token_enc:
        db.session.rollback()
        raise GoogleCalendarError(
            'Google did not return a refresh token. Remove TV Tracker’s access '
            'at myaccount.google.com/permissions and connect again.'
        )
    link.token_expires_at = _expires_at(tokens)
    link.updated_at = datetime.utcnow()
    db.session.commit()
    return user, kind


class GoogleCalendarClient:
    """Authenticated Calendar API calls for one connected account."""

    def __init__(self, access_token, refresh_token, expires_at, on_tokens=None):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self.on_tokens = on_tokens

    def _refresh(self) -> None:
        payload = _token_request({
            'client_id': _client_id(),
            'client_secret': _client_secret(),
            'refresh_token': self.refresh_token,
            'grant_type': 'refresh_token',
        })
        access = payload.get('access_token')
        if not access:
            raise GoogleCalendarError('Google refused to refresh the calendar login.')
        self.access_token = access
        if payload.get('refresh_token'):
            self.refresh_token = payload['refresh_token']
        self.expires_at = _expires_at(payload)
        if self.on_tokens:
            self.on_tokens(self.access_token, self.refresh_token, self.expires_at)

    def _ensure_token(self) -> None:
        if (
            self.access_token
            and self.expires_at
            and self.expires_at > datetime.utcnow() + timedelta(seconds=30)
        ):
            return
        self._refresh()

    def _request(self, method: str, url: str, **kwargs):
        self._ensure_token()
        headers = dict(kwargs.pop('headers', {}) or {})
        refreshed = False
        last_exc: Exception | None = None
        for attempt in range(3):
            headers['Authorization'] = f'Bearer {self.access_token}'
            try:
                resp = requests.request(method, url, headers=headers, timeout=20, **kwargs)
            except requests.RequestException as exc:
                last_exc = exc
                if attempt == 2:
                    raise GoogleCalendarError('Could not reach Google Calendar.') from exc
                time.sleep(0.4 * (attempt + 1))
                continue
            if resp.status_code == 401 and not refreshed:
                refreshed = True
                self._refresh()
                continue
            return resp
        raise GoogleCalendarError('Could not reach Google Calendar.') from last_exc

    def list_calendars(self) -> list[dict]:
        """Writable calendars: ``id``, ``name``, ``primary``."""
        calendars: list[dict] = []
        page_token = None
        for _ in range(10):
            params = {'minAccessRole': 'writer'}
            if page_token:
                params['pageToken'] = page_token
            resp = self._request(
                'GET', f'{CALENDAR_API}/users/me/calendarList', params=params,
            )
            if resp.status_code != 200:
                raise GoogleCalendarError(
                    'Could not list calendars on this Google account.',
                    status_code=resp.status_code,
                )
            payload = resp.json() or {}
            for item in payload.get('items') or []:
                cal_id = item.get('id')
                if not cal_id:
                    continue
                calendars.append({
                    'id': cal_id,
                    'name': item.get('summary') or cal_id,
                    'primary': bool(item.get('primary')),
                })
            page_token = payload.get('nextPageToken')
            if not page_token:
                break
        calendars.sort(key=lambda c: (not c['primary'], (c['name'] or '').lower()))
        return calendars

    def insert_event(self, calendar_id: str, body: dict) -> str:
        url = f'{CALENDAR_API}/calendars/{quote(calendar_id, safe="")}/events'
        resp = self._request('POST', url, json=body)
        if resp.status_code not in (200, 201):
            raise GoogleCalendarError(
                'Could not create the calendar meeting.',
                status_code=resp.status_code,
            )
        event_id = (resp.json() or {}).get('id')
        if not event_id:
            raise GoogleCalendarError('Google did not return a meeting id.')
        return str(event_id)

    def patch_event(self, calendar_id: str, event_id: str, body: dict) -> None:
        url = (
            f'{CALENDAR_API}/calendars/{quote(calendar_id, safe="")}'
            f'/events/{quote(event_id, safe="")}'
        )
        resp = self._request('PATCH', url, json=body)
        if resp.status_code == 404:
            raise GoogleCalendarError('Calendar meeting was deleted.', status_code=404)
        if resp.status_code not in (200, 201):
            raise GoogleCalendarError(
                'Could not update the calendar meeting.',
                status_code=resp.status_code,
            )

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        url = (
            f'{CALENDAR_API}/calendars/{quote(calendar_id, safe="")}'
            f'/events/{quote(event_id, safe="")}'
        )
        resp = self._request('DELETE', url)
        if resp.status_code in (204, 200, 404, 410):
            return
        raise GoogleCalendarError(
            'Could not remove the calendar meeting.',
            status_code=resp.status_code,
        )


def load_client(link: UserGoogleCalendar) -> GoogleCalendarClient:
    """Build a client and persist refreshed tokens back onto ``link``."""
    refresh = decrypt_token(link.refresh_token_enc)
    if not refresh:
        raise GoogleCalendarError('Connect the Google account again.')

    def _save(access, new_refresh, expires):
        link.access_token_enc = encrypt_token(access)
        link.refresh_token_enc = encrypt_token(new_refresh)
        link.token_expires_at = expires
        link.updated_at = datetime.utcnow()
        db.session.commit()

    return GoogleCalendarClient(
        access_token=decrypt_token(link.access_token_enc),
        refresh_token=refresh,
        expires_at=link.token_expires_at,
        on_tokens=_save,
    )
