from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime, timedelta
from enum import StrEnum
from urllib.parse import urlencode, urlsplit

from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.models import Session
from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from django.utils.http import url_has_allowed_host_and_scheme

INACTIVITY_SESSION_LIMIT = timedelta(minutes=30)
ABSOLUTE_SESSION_LIMIT = timedelta(hours=8)
SESSION_STARTED_AT_KEY = "accounts.session_started_at"
SESSION_LAST_ACTIVITY_KEY = "accounts.session_last_activity_at"


class SessionExpiryReason(StrEnum):
    """Stable values consumed by the future AUD-002 integration."""

    INACTIVITY = "inactivity"
    ABSOLUTE = "absolute"


def current_time() -> datetime:
    """Return the current aware time through a deterministic test seam."""
    return timezone.now()


def safe_local_destination(request: HttpRequest, candidate: str | None) -> str | None:
    """Accept only a same-host absolute-path destination."""
    if not candidate or "\\" in candidate:
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in candidate):
        return None
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return None
    if not url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return None
    return candidate


def establish_session_timestamps(request: HttpRequest) -> None:
    """Start the server-side inactivity and absolute clocks after authentication."""
    now = current_time().timestamp()
    request.session[SESSION_STARTED_AT_KEY] = now
    request.session[SESSION_LAST_ACTIVITY_KEY] = now
    request.session.set_expiry(math.ceil(INACTIVITY_SESSION_LIMIT.total_seconds()))


def notify_session_expired(*, user_id: int, reason: SessionExpiryReason) -> None:
    """No-persistence integration boundary implemented by AUD-002."""


def invalidate_user_sessions(user_id: int) -> int:
    """Delete every unexpired database session authenticated as the target user."""
    matching_keys: list[str] = []
    for session in Session.objects.filter(expire_date__gt=current_time()).iterator():
        if session.get_decoded().get(SESSION_KEY) == str(user_id):
            matching_keys.append(session.session_key)
    if matching_keys:
        Session.objects.filter(session_key__in=matching_keys).delete()
    return len(matching_keys)


def _expiry_reason(request: HttpRequest, now: datetime) -> SessionExpiryReason | None:
    started_at = request.session.get(SESSION_STARTED_AT_KEY)
    last_activity = request.session.get(SESSION_LAST_ACTIVITY_KEY)
    if not isinstance(started_at, (int, float)) or not isinstance(last_activity, (int, float)):
        establish_session_timestamps(request)
        return None

    absolute_age = now.timestamp() - started_at
    inactivity_age = now.timestamp() - last_activity
    if absolute_age >= ABSOLUTE_SESSION_LIMIT.total_seconds():
        return SessionExpiryReason.ABSOLUTE
    if inactivity_age >= INACTIVITY_SESSION_LIMIT.total_seconds():
        return SessionExpiryReason.INACTIVITY
    return None


def _reauthentication_url(request: HttpRequest) -> str:
    destination = safe_local_destination(request, request.get_full_path())
    query = urlencode({"next": destination}) if destination else ""
    base_url = reverse("accounts:session-expired")
    return f"{base_url}?{query}" if query else base_url


class SessionLifetimeMiddleware(MiddlewareMixin):
    """Deny expired authenticated sessions before protected view code executes."""

    def process_view(
        self,
        request: HttpRequest,
        view_func: Callable[..., HttpResponse],
        view_args: tuple[object, ...],
        view_kwargs: dict[str, object],
    ) -> HttpResponse | None:
        if request.user.is_authenticated:
            now = current_time()
            reason = _expiry_reason(request, now)
            if reason is not None:
                user_id = request.user.pk
                request.session.flush()
                notify_session_expired(user_id=user_id, reason=reason)
                redirect_url = _reauthentication_url(request)
                if request.headers.get("HX-Request") == "true":
                    response = HttpResponse(status=401)
                    response.headers["HX-Redirect"] = redirect_url
                else:
                    response = HttpResponse(status=302)
                    response.headers["Location"] = redirect_url
                response.headers["Cache-Control"] = "no-store"
                return response

            started_at = request.session.get(SESSION_STARTED_AT_KEY)
            if isinstance(started_at, (int, float)):
                request.session[SESSION_LAST_ACTIVITY_KEY] = now.timestamp()
                remaining_absolute = ABSOLUTE_SESSION_LIMIT.total_seconds() - (
                    now.timestamp() - started_at
                )
                request.session.set_expiry(
                    max(
                        1,
                        math.ceil(
                            min(
                                INACTIVITY_SESSION_LIMIT.total_seconds(),
                                remaining_absolute,
                            )
                        ),
                    )
                )
        return None
