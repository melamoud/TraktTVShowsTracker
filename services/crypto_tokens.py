"""
Encrypt / decrypt Trakt OAuth tokens at rest using Fernet.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


def _fernet():
    """Build a Fernet instance from the app SECRET_KEY."""
    digest = hashlib.sha256(current_app.config['SECRET_KEY'].encode('utf-8')).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_token(plain: str | None) -> str | None:
    """Encrypt a token string for DB storage."""
    if not plain:
        return None
    return _fernet().encrypt(plain.encode('utf-8')).decode('utf-8')


def decrypt_token(cipher: str | None) -> str | None:
    """Decrypt a token string from DB storage."""
    if not cipher:
        return None
    try:
        return _fernet().decrypt(cipher.encode('utf-8')).decode('utf-8')
    except InvalidToken:
        return None
