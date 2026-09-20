"""CSRF protection for every state-changing request (FR-36).

Cubit's server listens on the loopback interface, but that is not a boundary a
browser respects: any page the user has open can POST to ``127.0.0.1:8000``.
A token tied to the session, checked on every unsafe method, is what stops it.
"""

from __future__ import annotations

import secrets

from flask import abort, request, session

#: Where the token lives in the session cookie, and what the form field is called.
SESSION_KEY = "csrf_token"
FIELD_NAME = "csrf_token"

#: Methods that may change something and therefore need a token.
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def csrf_token() -> str:
    """The session's token, minted on first use."""
    token = session.get(SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[SESSION_KEY] = token
    return token


def check_csrf() -> None:
    """Reject an unsafe request that did not carry the session's token."""
    if request.method not in UNSAFE_METHODS:
        return

    expected = session.get(SESSION_KEY)
    sent = request.form.get(FIELD_NAME) or request.headers.get("X-CSRF-Token", "")
    if not expected or not sent or not secrets.compare_digest(str(expected), str(sent)):
        abort(400, "This form has expired or came from somewhere else. Reload and try again.")
