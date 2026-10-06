"""Kimi (Moonshot AI) Coding API quota, rate limits and models.

Ported from kimi-quota (https://github.com/SeeYangZhi/kimi-quota).
"""

from __future__ import annotations

import argparse
import os
from typing import Any, Optional

from .. import core
from ..core import Provider, fmt_sgt, pct

DEFAULT_BASE_URL = "https://api.kimi.com/coding/v1"
ENV_VARS = ("MOONSHOT_API_KEY", "KIMI_API_KEY")
BASE_URL_ENV = "KIMI_BASE_URL"
TIMEOUT = 15


def get_base_url(cli_url: Optional[str] = None) -> str:
    """Resolve base URL: --base-url > KIMI_BASE_URL > default."""
    if cli_url:
        return cli_url.rstrip("/")
    env_url = os.environ.get(BASE_URL_ENV, "").strip()
    if env_url:
        return env_url.rstrip("/")
    return DEFAULT_BASE_URL


def print_quota(data: dict) -> None:
    """Print the human-readable quota report for a ``/usages`` response."""
    sub_type = data.get("subType", "unknown")
    is_paid = sub_type == "TYPE_PURCHASE"

    # Daily/weekly usage
    usage = data.get("usage", {})
    u_limit = int(usage.get("limit", 0))
    u_remaining = int(usage.get("remaining", 0))
    u_used = u_limit - u_remaining
    u_reset = usage.get("resetTime", "")

    # Rate limit (rolling window)
    limits = data.get("limits", [])
    rate_info = ""
    if limits:
        lim = limits[0]
        window = lim.get("window", {})
        duration = window.get("duration", 0)
        unit = window.get("timeUnit", "").replace("TIME_UNIT_", "").lower()
        detail = lim.get("detail", {})
        r_limit = int(detail.get("limit", 0))
        r_remaining = int(detail.get("remaining", 0))
        r_used = r_limit - r_remaining
        r_reset = detail.get("resetTime", "")
        rate_info = (
            f"\n📊 Rate Limit ({duration}{unit} rolling window):\n"
            f"   Used: {r_used}/{r_limit} ({pct(r_used, r_limit)}%)\n"
            f"   Remaining: {r_remaining}\n"
            f"   Resets: {fmt_sgt(r_reset)}"
        )

    # Parallel requests
    parallel = data.get("parallel", {})
    p_limit = parallel.get("limit", "?")

    # Membership level
    membership = data.get("user", {}).get("membership", {})
    level = membership.get("level", "unknown").replace("LEVEL_", "")

    plan_label = "Paid" if is_paid else "Free"

    print("🔑 Kimi Coding API — Quota Report")
    print(f"   Plan: {plan_label} ({level})")
    print("")
    print("📋 Weekly Quota:")
    print(f"   Used: {u_used}/{u_limit} ({pct(u_used, u_limit)}%)")
    print(f"   Remaining: {u_remaining}")
    print(f"   Resets: {fmt_sgt(u_reset)}")
    if rate_info:
        print(rate_info)
    print(f"\n⚡ Max Parallel Requests: {p_limit}")

    # Alert if quota low
    if u_limit > 0 and u_remaining / u_limit < 0.2:
        print(f"\n⚠️  Low quota: only {u_remaining}/{u_limit} remaining ({pct(u_used, u_limit)}% used)!")


def print_models(data: dict) -> None:
    """Print the model list for a ``/models`` response."""
    models = data.get("data", [])
    if not models:
        print("No models found.")
        return

    print(f"🤖 Available Models ({len(models)}):\n")
    for m in models:
        mid = m.get("id", "?")
        owner = m.get("owned_by", "?")
        print(f"   • {mid} (by {owner})")


class KimiProvider(Provider):
    name = "kimi"
    description = "Kimi (Moonshot AI) Coding API quota, rate limits and models"
    env_vars = ENV_VARS
    missing_key_message = (
        "No API key found. Set MOONSHOT_API_KEY or KIMI_API_KEY env var, or use --key."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--models", action="store_true", help="List available models")
        parser.add_argument(
            "--base-url",
            help=f"Base URL (default: {DEFAULT_BASE_URL}, or {BASE_URL_ENV} env var)",
        )

    def fetch(self, key: str, args: argparse.Namespace) -> Any:
        base_url = get_base_url(getattr(args, "base_url", None))
        path = "/models" if getattr(args, "models", False) else "/usages"
        return core.fetch_json(f"{base_url}{path}", key, timeout=TIMEOUT, label="Kimi")

    def render(self, payload: Any, args: argparse.Namespace) -> None:
        if getattr(args, "models", False):
            print_models(payload)
        else:
            print_quota(payload)


PROVIDER = KimiProvider()
