"""Shared fixtures. Every test is offline: urlopen is disabled globally."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List

import pytest

from check_llm_quota import core

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if anything tries to hit the network."""

    def _blocked(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("network access attempted during an offline test")

    monkeypatch.setattr(urllib.request, "urlopen", _blocked)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Strip provider env vars and point the Hermes auth file at an empty tmp path."""
    for var in ("ZAI_API_KEY", "MOONSHOT_API_KEY", "KIMI_API_KEY", "KIMI_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(core, "hermes_auth_path", lambda: tmp_path / "missing-auth.json")


@pytest.fixture
def fake_fetch(monkeypatch: pytest.MonkeyPatch) -> Callable[[Dict[str, Any]], List[str]]:
    """Replace ``core.fetch_json`` with a URL-substring -> fixture lookup.

    Returns the list of URLs requested so tests can assert on routing.
    Values may be a fixture filename, a dict/list payload, or an exception
    instance to raise.
    """

    def install(routes: Dict[str, Any]) -> List[str]:
        calls: List[str] = []

        def _fetch(urls: Any, api_key: str, **kwargs: Any) -> Any:
            url_list = [urls] if isinstance(urls, str) else list(urls)
            calls.extend(url_list)
            for url in url_list:
                for needle, value in routes.items():
                    if needle in url:
                        if isinstance(value, Exception):
                            raise value
                        if isinstance(value, str):
                            return load_fixture(value)
                        return value
            raise AssertionError(f"unexpected URL(s) {url_list!r}")

        monkeypatch.setattr(core, "fetch_json", _fetch)
        return calls

    return install
