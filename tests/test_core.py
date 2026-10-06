"""Tests for the provider-agnostic helpers in check_llm_quota.core."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import pytest

from check_llm_quota import core
from check_llm_quota.core import SGT, QuotaError

from conftest import FIXTURES


# --- key resolution --------------------------------------------------------


def test_resolve_key_prefers_cli(monkeypatch):
    monkeypatch.setenv("ZAI_API_KEY", "from-env")
    assert core.resolve_key("from-cli", ("ZAI_API_KEY",)) == "from-cli"


def test_resolve_key_env_order_and_blank_skipped(monkeypatch):
    monkeypatch.setenv("MOONSHOT_API_KEY", "   ")
    monkeypatch.setenv("KIMI_API_KEY", "kimi-env")
    assert core.resolve_key(None, ("MOONSHOT_API_KEY", "KIMI_API_KEY")) == "kimi-env"


def test_resolve_key_none_when_unset():
    assert core.resolve_key(None, ("ZAI_API_KEY",)) is None
    assert core.resolve_key(None, ("ZAI_API_KEY",), hermes_pool="zai") is None


def test_hermes_pool_skips_blank_tokens():
    key = core.hermes_pool_key("zai", FIXTURES / "hermes_auth.json")
    assert key == "pool-token-zai"


def test_hermes_pool_legacy_top_level_list():
    assert core.hermes_pool_key("legacy", FIXTURES / "hermes_auth.json") == "legacy-token"


def test_hermes_pool_missing_or_corrupt(tmp_path: Path):
    assert core.hermes_pool_key("zai", tmp_path / "nope.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert core.hermes_pool_key("zai", bad) is None
    not_dict = tmp_path / "list.json"
    not_dict.write_text("[1, 2]")
    assert core.hermes_pool_key("zai", not_dict) is None


def test_resolve_key_falls_back_to_hermes(monkeypatch):
    monkeypatch.setattr(core, "hermes_auth_path", lambda: FIXTURES / "hermes_auth.json")
    assert core.resolve_key(None, ("ZAI_API_KEY",), hermes_pool="zai") == "pool-token-zai"


# --- formatting ------------------------------------------------------------


def test_format_reset_buckets():
    now = datetime(2026, 4, 16, 10, 0, tzinfo=SGT)
    ms = lambda dt: int(dt.timestamp() * 1000)  # noqa: E731
    assert core.format_reset(ms(datetime(2026, 4, 16, 9, 0, tzinfo=SGT)), now) == "now"
    assert core.format_reset(ms(datetime(2026, 4, 16, 10, 45, tzinfo=SGT)), now) == "in 45m"
    assert core.format_reset(ms(datetime(2026, 4, 16, 13, 30, tzinfo=SGT)), now) == "in 3h"
    assert core.format_reset(ms(datetime(2026, 4, 18, 10, 31, tzinfo=SGT)), now) == "2026-04-18 10:31 SGT"


def test_format_reset_bad_input():
    assert core.format_reset(None) == "N/A"
    assert core.format_reset("soon") == "N/A"


def test_fmt_sgt():
    assert core.fmt_sgt("2026-06-21T00:14:00Z") == "2026-06-21 08:14 SGT"
    assert core.fmt_sgt("garbage") == "garbage"
    assert core.fmt_sgt(None) is None


@pytest.mark.parametrize("value,expected", [(0, "green"), (49.9, "green"), (50, "yellow"), (79, "yellow"), (80, "red"), (100, "red")])
def test_pct_status(value, expected):
    assert core.pct_status(value) == expected


def test_pct():
    assert core.pct(20, 100) == 20
    assert core.pct(1, 3) == 33
    assert core.pct(5, 0) == 0
    assert core.pct(5, "abc") == 0
    assert core.pct(5, "10") == 50


# --- HTTP fallback (fake urlopen, still offline) ---------------------------


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _http_error(url: str, code: int, body: bytes = b"") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "reason", {}, io.BytesIO(body))


def _install_urlopen(monkeypatch, behaviours):
    """``behaviours`` maps URL -> payload dict | Exception."""
    seen = []

    def _urlopen(req, timeout=None):
        url = req.full_url
        seen.append((url, req.get_header("Authorization"), timeout))
        result = behaviours[url]
        if isinstance(result, Exception):
            raise result
        return _Resp(json.dumps(result).encode())

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    return seen


def test_fetch_json_first_url_ok(monkeypatch):
    seen = _install_urlopen(monkeypatch, {"https://a/x": {"ok": 1}})
    assert core.fetch_json("https://a/x", "KEY", timeout=3) == {"ok": 1}
    assert seen == [("https://a/x", "Bearer KEY", 3)]


def test_fetch_json_404_then_fallback(monkeypatch):
    seen = _install_urlopen(
        monkeypatch,
        {"https://a/x": _http_error("https://a/x", 404), "https://b/x": {"ok": 2}},
    )
    assert core.fetch_json(["https://a/x", "https://b/x"], "KEY") == {"ok": 2}
    assert [s[0] for s in seen] == ["https://a/x", "https://b/x"]


def test_fetch_json_connection_error_then_fallback(monkeypatch):
    _install_urlopen(
        monkeypatch,
        {"https://a/x": urllib.error.URLError("dns"), "https://b/x": {"ok": 3}},
    )
    assert core.fetch_json(["https://a/x", "https://b/x"], "KEY") == {"ok": 3}


def test_fetch_json_401_stops_immediately(monkeypatch):
    seen = _install_urlopen(
        monkeypatch,
        {"https://a/x": _http_error("https://a/x", 401, b'{"error":"bad key"}'), "https://b/x": {"ok": 1}},
    )
    with pytest.raises(QuotaError) as ei:
        core.fetch_json(["https://a/x", "https://b/x"], "KEY")
    assert "Authentication failed" in str(ei.value)
    assert "bad key" in str(ei.value)
    assert len(seen) == 1


def test_fetch_json_other_http_error(monkeypatch):
    _install_urlopen(monkeypatch, {"https://a/x": _http_error("https://a/x", 500, b"boom")})
    with pytest.raises(QuotaError, match="HTTP 500: boom"):
        core.fetch_json("https://a/x", "KEY")


def test_fetch_json_single_url_connection_error_is_direct(monkeypatch):
    _install_urlopen(monkeypatch, {"https://a/x": urllib.error.URLError("refused")})
    with pytest.raises(QuotaError, match="Connection error: refused"):
        core.fetch_json("https://a/x", "KEY")


def test_fetch_json_all_exhausted(monkeypatch):
    _install_urlopen(
        monkeypatch,
        {"https://a/x": _http_error("https://a/x", 404), "https://b/x": urllib.error.URLError("nope")},
    )
    with pytest.raises(QuotaError, match="Could not reach any Z.ai endpoint"):
        core.fetch_json(["https://a/x", "https://b/x"], "KEY", label="Z.ai")


def test_fetch_json_invalid_json(monkeypatch):
    def _urlopen(req, timeout=None):
        return _Resp(b"<html>")

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    with pytest.raises(QuotaError, match="Invalid JSON"):
        core.fetch_json("https://a/x", "KEY")


def test_fetch_json_no_urls():
    with pytest.raises(QuotaError):
        core.fetch_json([], "KEY")
