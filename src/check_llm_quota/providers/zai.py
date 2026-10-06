"""Z.ai (Zhipu AI) GLM Coding Plan quota and supported models.

Ported from zai-quota (https://github.com/SeeYangZhi/zai-quota).
"""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any, Dict, List, Optional

from .. import core
from ..core import SGT, Provider, QuotaError, format_reset, pct_status

QUOTA_ENDPOINTS = {
    "intl": "https://api.z.ai/api/monitor/usage/quota/limit",
    "cn": "https://open.bigmodel.cn/api/monitor/usage/quota/limit",
}

MODELS_ENDPOINTS = {
    "intl": "https://api.z.ai/api/paas/v4/models",
    "cn": "https://open.bigmodel.cn/api/paas/v4/models",
}

ENV_VARS = ("ZAI_API_KEY",)
HERMES_POOL = "zai"
TIMEOUT = 10

# Plan-to-model mapping from https://z.ai/subscribe
# Updated as of 2026-04
PLAN_MODELS = {
    "lite": {
        "GLM-5.1", "GLM-5-Turbo", "GLM-4.7", "GLM-4.6", "GLM-4.5-Air",
        "GLM-4.6V",
    },
    "standard": {  # Pro
        "GLM-5.1", "GLM-5-Turbo", "GLM-4.7", "GLM-4.6", "GLM-4.5-Air",
        "GLM-5", "GLM-5-Code", "GLM-4.5",
        "GLM-4.6V", "GLM-5V-Turbo",
    },
    "pro": {  # Max
        "GLM-5.1", "GLM-5-Turbo", "GLM-4.7", "GLM-4.6", "GLM-4.5-Air",
        "GLM-5", "GLM-5-Code", "GLM-4.5",
        "GLM-4.6V", "GLM-5V-Turbo",
    },
}

TYPE_LABELS = {
    "TIME_LIMIT": "Time Limit",
    "TOKENS_LIMIT": "Tokens",
    "RATE_LIMIT": "Rate Limit",
    "TIMES_LIMIT": "Requests",
    "SESSION_LIMIT": "Sessions",
}

PLAN_LABELS = {"lite": "Lite", "standard": "Pro", "pro": "Max"}
LEVEL_LABELS = {"lite": "Lite", "standard": "Standard", "pro": "Pro"}


def endpoint_urls(table: Dict[str, str], endpoint: Optional[str] = None) -> List[str]:
    """URLs to try: just the forced endpoint, or every endpoint in order (intl, cn)."""
    return [table[endpoint]] if endpoint else list(table.values())


def build_model_list(models_data: dict, plan: str = "") -> list:
    """Merge API-returned models with plan-based model list."""
    api_ids = set()
    models = []
    for m in models_data.get("data", []):
        mid = m.get("id", "")
        api_ids.add(mid.lower())
        models.append({"id": mid, "object": "model", "created": m.get("created"), "source": "api"})

    # Add all known models that the API didn't return
    allowed = set()
    for pk in PLAN_MODELS:
        for m in PLAN_MODELS[pk]:
            allowed.add(m.lower())

    for mid_lower in allowed:
        if mid_lower not in api_ids:
            models.append({"id": mid_lower, "object": "model", "created": None, "source": "plan"})

    return models


def print_models(models_data: dict, plan: str = ""):
    """Print supported models grouped by access status."""
    models = build_model_list(models_data, plan)
    if not models:
        print("  No models found.")
        return

    # Determine which models the current plan grants
    plan_key = plan.lower() if plan else ""
    plan_set = set()
    if plan_key and plan_key in PLAN_MODELS:
        plan_set = PLAN_MODELS[plan_key]

    # Sort alphabetically
    models.sort(key=lambda m: m.get("id", "").lower())

    plan_label = PLAN_LABELS.get(plan_key, plan or "Unknown")

    print("  Z.ai GLM Models")
    print(f"  Plan: {plan_label}")
    print("  " + "-" * 40)

    accessible = []
    not_accessible = []
    for m in models:
        mid = m.get("id", "")
        has_access = mid.lower() in {x.lower() for x in plan_set} if plan_set else None
        entry = {
            "id": mid,
            "source": m.get("source", "api"),
            "created": m.get("created"),
            "access": has_access,
        }
        if has_access is True:
            accessible.append(entry)
        elif has_access is False:
            not_accessible.append(entry)
        else:
            # No plan detected, list all as unknown
            accessible.append(entry)

    # Show accessible models
    for e in accessible:
        mid = e["id"]
        tag = ""
        if e["source"] == "plan":
            tag = " *"
        date_str = ""
        if e["created"]:
            try:
                date_str = datetime.fromtimestamp(e["created"], tz=SGT).strftime("%Y-%m-%d")
            except (OSError, ValueError, TypeError):
                pass
        access = "[ok]     "
        print(f"    {access} {mid:<16} {date_str}{tag}")

    # Show models on higher plans
    if not_accessible:
        print("\n  Available on higher plans:")
        for e in not_accessible:
            mid = e["id"]
            # Find which plan has this
            for pk, pmodels in PLAN_MODELS.items():
                if mid.lower() in {x.lower() for x in pmodels}:
                    upgrade = PLAN_LABELS.get(pk, pk)
                    print(f"    [locked] {mid:<16} requires {upgrade}")
                    break

    print(f"\n  Total: {len(models)} models")
    if plan_set:
        print(f"  {len(accessible)} accessible on your plan, {len(not_accessible)} require upgrade")
    else:
        print("  * Not returned by /v4/models API, known from plan")
    print("  ! Model access based on z.ai/subscribe, may differ from actual")

    return models


def print_quota(data: dict):
    """Print human-readable quota summary."""
    raw = data.get("data", data)
    limits = raw.get("limits", [])
    level = raw.get("level", "Unknown")

    level_str = LEVEL_LABELS.get(level, level)

    print("  Z.ai GLM Quota")
    print(f"  Plan: {level_str}")
    print("  " + "-" * 37)

    if not limits:
        print("  No quota limits found.")
        return

    for lim in limits:
        ltype = lim.get("type", "UNKNOWN")
        pct = lim.get("percentage", 0)
        label = TYPE_LABELS.get(ltype, ltype.replace("_", " ").title())
        status = pct_status(pct)
        remaining = lim.get("remaining", 0)
        reset = lim.get("nextResetTime")

        print(f"  [{status}] {label}")
        print(f"     Used: {pct}%{f' | Remaining: {remaining}' if remaining else ''}")

        details = lim.get("usageDetails", [])
        if details:
            for d in details:
                model = d.get("modelCode", "?")
                u = d.get("usage", 0)
                print(f"       - {model}: {u}")

        if reset:
            print(f"     Resets: {format_reset(reset)}")
        print()

    print("  " + "-" * 37)


def plan_from_quota(quota_data: Any) -> str:
    if not isinstance(quota_data, dict):
        return ""
    return quota_data.get("data", quota_data).get("level", "") or ""


class ZaiProvider(Provider):
    name = "zai"
    description = "Z.ai (Zhipu AI) GLM Coding Plan quota and supported models"
    env_vars = ENV_VARS
    hermes_pool = HERMES_POOL
    missing_key_message = (
        "No Z.ai API key found.\n"
        "  Pass --key, set ZAI_API_KEY env var, or configure in Hermes auth.json."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--models", "-m", action="store_true", help="List supported models")
        parser.add_argument(
            "--endpoint", "-e",
            choices=["intl", "cn"],
            help="Force a specific endpoint (intl=api.z.ai, cn=open.bigmodel.cn)",
        )

    def fetch(self, key: str, args: argparse.Namespace) -> Any:
        endpoint = getattr(args, "endpoint", None)
        if getattr(args, "models", False):
            # Fetch both models list and quota (for plan detection)
            models_data = core.fetch_json(
                endpoint_urls(MODELS_ENDPOINTS, endpoint), key, timeout=TIMEOUT, label="Z.ai"
            )
            try:
                quota_data = core.fetch_json(
                    endpoint_urls(QUOTA_ENDPOINTS, endpoint), key, timeout=TIMEOUT, label="Z.ai"
                )
                plan = plan_from_quota(quota_data)
            except QuotaError:
                plan = ""
            return {"models": models_data, "plan": plan}
        return core.fetch_json(
            endpoint_urls(QUOTA_ENDPOINTS, endpoint), key, timeout=TIMEOUT, label="Z.ai"
        )

    def render(self, payload: Any, args: argparse.Namespace) -> None:
        if getattr(args, "models", False):
            print_models(payload["models"], payload["plan"])
        else:
            print_quota(payload)

    def to_json(self, payload: Any, args: argparse.Namespace) -> Any:
        if getattr(args, "models", False):
            return build_model_list(payload["models"], payload["plan"])
        return payload


PROVIDER = ZaiProvider()
