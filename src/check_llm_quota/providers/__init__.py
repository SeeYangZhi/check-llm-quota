"""Provider registry.

Every module in this package (other than ``_``-prefixed ones) that defines a
module-level ``PROVIDER`` instance of :class:`check_llm_quota.core.Provider`
is registered automatically. Adding a provider means adding one file here.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Dict, Iterator

from ..core import Provider


def iter_providers() -> Iterator[Provider]:
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        provider = getattr(module, "PROVIDER", None)
        if isinstance(provider, Provider) and provider.name:
            yield provider


def get_providers() -> Dict[str, Provider]:
    """Return ``{name: provider}`` sorted by name (deterministic ``all`` order)."""
    return {p.name: p for p in sorted(iter_providers(), key=lambda p: p.name)}


__all__ = ["Provider", "get_providers", "iter_providers"]
