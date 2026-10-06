"""Shared helpers for all providers: key resolution, HTTP, formatting.

Everything here is stdlib only (urllib, json, datetime). Providers subclass
:class:`Provider` and use these helpers so that behaviour (env-var lookup,
Hermes ``auth.json`` pool, multi-URL fallback, SGT time formatting, colour
thresholds) stays consistent across the CLI.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence, Union

SGT = timezone(timedelta(hours=8))
"""Singapore time; both upstream scripts render reset times in SGT."""


class QuotaError(Exception):
    """A user-facing failure (missing key, HTTP error, unreachable endpoint).

    Providers raise this instead of calling ``sys.exit`` so that ``all`` can
    isolate one provider's failure from the others.
    """


# ---------------------------------------------------------------------------
# Key resolution
# ---------------------------------------------------------------------------


def hermes_auth_path() -> Path:
    """Location of the Hermes Agent credential file (``~/.hermes/auth.json``)."""
    return Path.home() / ".hermes" / "auth.json"


def hermes_pool_key(pool_name: str, auth_file: Optional[Path] = None) -> Optional[str]:
    """Return the first usable token for ``pool_name`` from Hermes ``auth.json``.

    Mirrors the original zai-quota logic: look in ``credential_pool[pool_name]``
    first, then a legacy top-level ``[pool_name]`` list. Entries may be dicts
    with an ``access_token`` or plain strings.
    """
    path = auth_file if auth_file is not None else hermes_auth_path()
    if not path.exists():
        return None
    try:
        auth = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(auth, dict):
        return None

    pool = auth.get("credential_pool", {})
    if not isinstance(pool, dict):
        pool = {}
    keys = pool.get(pool_name, auth.get(pool_name, []))
    if not isinstance(keys, list):
        return None

    for entry in keys:
        if isinstance(entry, dict):
            token = entry.get("access_token")
            if token:
                return token
        elif isinstance(entry, str) and entry:
            return entry
    return None


def resolve_key(
    cli_key: Optional[str],
    env_vars: Sequence[str],
    hermes_pool: Optional[str] = None,
    auth_file: Optional[Path] = None,
) -> Optional[str]:
    """Resolve an API key: CLI arg > env vars (in order) > Hermes pool.

    ``env_vars`` is checked in order; blank values are ignored. If
    ``hermes_pool`` is given, ``~/.hermes/auth.json`` is consulted last.
    Returns ``None`` when nothing is configured.
    """
    if cli_key:
        return cli_key
    for var in env_vars:
        val = os.environ.get(var, "").strip()
        if val:
            return val
    if hermes_pool:
        return hermes_pool_key(hermes_pool, auth_file)
    return None


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _read_error_body(err: urllib.error.HTTPError) -> str:
    try:
        if err.fp is None:
            return ""
        return err.read().decode(errors="replace").strip()
    except Exception:  # pragma: no cover - defensive
        return ""


def fetch_json(
    urls: Union[str, Iterable[str]],
    api_key: str,
    *,
    timeout: float = 10,
    label: str = "API",
) -> Any:
    """GET JSON from the first reachable URL using a Bearer token.

    Fallback rules (from the original zai-quota script):

    * HTTP 401 -> raise :class:`QuotaError` immediately (bad key).
    * HTTP 404 or a connection error -> try the next URL.
    * Any other HTTP error -> raise :class:`QuotaError` with the body/reason.
    * All URLs exhausted -> raise :class:`QuotaError`.

    With a single URL the connection error is reported directly (kimi-quota
    behaviour); with several URLs a "could not reach any endpoint" summary is
    raised instead.
    """
    url_list = [urls] if isinstance(urls, str) else list(urls)
    if not url_list:
        raise QuotaError(f"No {label} endpoint configured.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    last_error: Optional[str] = None
    for url in url_list:
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode()
        except urllib.error.HTTPError as e:
            body = _read_error_body(e)
            if e.code == 401:
                msg = "Authentication failed - API key may be invalid or expired."
                if body:
                    msg += f"\n  HTTP 401: {body}"
                raise QuotaError(msg)
            if e.code == 404:
                last_error = f"HTTP 404: {e.reason}"
                continue
            raise QuotaError(f"HTTP {e.code}: {body or e.reason}")
        except urllib.error.URLError as e:
            last_error = f"Connection error: {e.reason}"
            continue
        except OSError as e:  # socket.timeout and friends
            last_error = f"Connection error: {e}"
            continue

        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise QuotaError(f"Invalid JSON response from {url}: {e}")

    if len(url_list) == 1 and last_error:
        raise QuotaError(last_error)
    detail = f" ({last_error})" if last_error else ""
    raise QuotaError(f"Could not reach any {label} endpoint.{detail}")


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_reset(ts_ms: Any, now: Optional[datetime] = None) -> str:
    """Format a millisecond epoch timestamp as a relative/absolute SGT reset time.

    ``< 1h`` -> ``in Nm``; ``< 24h`` -> ``in Nh``; otherwise ``YYYY-MM-DD HH:MM SGT``.
    Past timestamps return ``"now"``; unparseable input returns ``"N/A"``.
    """
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=SGT)
        current = now if now is not None else datetime.now(tz=SGT)
        diff = dt - current
        if diff.total_seconds() < 0:
            return "now"
        if diff.total_seconds() < 3600:
            return f"in {int(diff.total_seconds() // 60)}m"
        if diff.total_seconds() < 86400:
            return f"in {int(diff.total_seconds() // 3600)}h"
        return dt.strftime("%Y-%m-%d %H:%M SGT")
    except (OSError, ValueError, TypeError, OverflowError):
        return "N/A"


def fmt_sgt(iso_str: Any) -> str:
    """Convert an ISO-8601 UTC timestamp (``...Z``) to ``YYYY-MM-DD HH:MM SGT``.

    Returns the input unchanged if it cannot be parsed.
    """
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        return dt.astimezone(SGT).strftime("%Y-%m-%d %H:%M SGT")
    except Exception:
        return iso_str


def pct_status(pct: float) -> str:
    """Map a used-percentage to ``green`` (<50), ``yellow`` (<80) or ``red``."""
    if pct < 50:
        return "green"
    if pct < 80:
        return "yellow"
    return "red"


def pct(used: float, total: Any) -> int:
    """Integer percentage of ``used`` over ``total`` (0 when total is 0/invalid)."""
    try:
        total = int(total)
    except (TypeError, ValueError):
        return 0
    if total == 0:
        return 0
    return round((used / total) * 100)


# ---------------------------------------------------------------------------
# Provider base class
# ---------------------------------------------------------------------------


class Provider:
    """Base class for a quota provider.

    Subclass it in ``check_llm_quota/providers/<name>.py`` and expose an
    instance as the module-level ``PROVIDER``; the registry picks it up
    automatically.
    """

    #: Subcommand name, e.g. ``"zai"``.
    name: str = ""
    #: One-line help shown in ``check-llm-quota --help``.
    description: str = ""
    #: Environment variables consulted for the API key, in priority order.
    env_vars: Sequence[str] = ()
    #: Optional Hermes ``auth.json`` credential-pool name.
    hermes_pool: Optional[str] = None
    #: Message printed to stderr when no key could be resolved.
    missing_key_message: str = "No API key found."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add provider-specific flags (``--key``/``--json`` are added for you)."""

    def resolve_key(self, cli_key: Optional[str] = None) -> Optional[str]:
        return resolve_key(cli_key, self.env_vars, self.hermes_pool)

    def is_configured(self) -> bool:
        """True if a key is available without a ``--key`` argument."""
        return bool(self.resolve_key(None))

    def fetch(self, key: str, args: argparse.Namespace) -> Any:
        """Call the provider API and return a payload (dict/list)."""
        raise NotImplementedError

    def render(self, payload: Any, args: argparse.Namespace) -> None:
        """Print the human-readable report for ``payload``."""
        raise NotImplementedError

    def to_json(self, payload: Any, args: argparse.Namespace) -> Any:
        """Return what ``--json`` should dump (defaults to the payload itself)."""
        return payload
