"""Renderer tests for the Z.ai provider, driven by fixture JSON."""

from __future__ import annotations

import argparse
import re
from datetime import datetime

import pytest

from check_llm_quota import core
from check_llm_quota.core import SGT
from check_llm_quota.providers import zai

from conftest import load_fixture


def test_endpoint_urls():
    assert zai.endpoint_urls(zai.QUOTA_ENDPOINTS) == [
        "https://api.z.ai/api/monitor/usage/quota/limit",
        "https://open.bigmodel.cn/api/monitor/usage/quota/limit",
    ]
    assert zai.endpoint_urls(zai.QUOTA_ENDPOINTS, "cn") == [
        "https://open.bigmodel.cn/api/monitor/usage/quota/limit"
    ]


def test_print_quota(capsys, monkeypatch):
    # Pin "now" so relative reset strings are deterministic.
    fixed_now = datetime(2026, 4, 15, 10, 0, tzinfo=SGT)
    monkeypatch.setattr(zai, "format_reset", lambda ts: core.format_reset(ts, fixed_now))

    zai.print_quota(load_fixture("zai_quota.json"))
    out = capsys.readouterr().out

    assert "Z.ai GLM Quota" in out
    assert "Plan: Lite" in out
    assert "[green] Time Limit" in out
    assert "Used: 0%" in out
    assert "Remaining: 100" in out
    assert "- search-prime: 0" in out
    assert "- zread: 0" in out
    assert "Resets: 2026-04-16 10:31 SGT" in out
    assert "[green] Tokens" in out
    assert "Used: 18%\n" in out
    assert "[red] Sessions" in out
    assert "Used: 85% | Remaining: 3" in out


def test_print_quota_no_limits(capsys):
    zai.print_quota({"data": {"level": "pro", "limits": []}})
    out = capsys.readouterr().out
    assert "Plan: Pro" in out
    assert "No quota limits found." in out


def test_print_quota_accepts_unwrapped_payload(capsys):
    zai.print_quota({"level": "weird", "limits": [{"type": "FOO_BAR", "percentage": 60}]})
    out = capsys.readouterr().out
    assert "Plan: weird" in out
    assert "[yellow] Foo Bar" in out


def test_build_model_list_merges_plan_models():
    models = zai.build_model_list(load_fixture("zai_models.json"), "lite")
    ids = {m["id"].lower(): m for m in models}
    assert ids["glm-4.6"]["source"] == "api"
    assert ids["glm-4.6"]["created"] == 1759190400
    assert ids["glm-5.1"]["source"] == "plan"
    assert ids["glm-5.1"]["created"] is None
    all_known = {m.lower() for s in zai.PLAN_MODELS.values() for m in s}
    assert set(ids) == all_known | {"glm-4.5-air", "glm-4.6", "glm-5"}


def test_print_models_lite_plan(capsys):
    zai.print_models(load_fixture("zai_models.json"), "lite")
    out = capsys.readouterr().out
    assert "Plan: Lite" in out
    assert "[ok]      GLM-4.6          2025-09-30" in out
    assert re.search(r"\[ok\]\s+glm-5\.1\s+\*$", out, re.M), out
    assert "Available on higher plans:" in out
    assert "[locked] GLM-5            requires Pro" in out
    assert "require upgrade" in out


def test_print_models_unknown_plan(capsys):
    zai.print_models(load_fixture("zai_models.json"), "")
    out = capsys.readouterr().out
    assert "Plan: Unknown" in out
    assert "[locked]" not in out
    assert "* Not returned by /v4/models API" in out


def test_print_models_empty(capsys):
    zai.PLAN_MODELS  # plan models always pad the list, so force an empty merge
    assert zai.build_model_list({"data": []}) != []
    zai.print_models({"data": []}, "")
    assert "Total:" in capsys.readouterr().out


def test_plan_from_quota():
    assert zai.plan_from_quota(load_fixture("zai_quota.json")) == "lite"
    assert zai.plan_from_quota({"level": "pro"}) == "pro"
    assert zai.plan_from_quota(None) == ""
    assert zai.plan_from_quota({}) == ""


def test_provider_fetch_quota_routes_both_endpoints(fake_fetch):
    calls = fake_fetch({"/quota/limit": "zai_quota.json"})
    args = argparse.Namespace(models=False, endpoint=None)
    payload = zai.PROVIDER.fetch("k", args)
    assert payload["data"]["level"] == "lite"
    assert calls == zai.endpoint_urls(zai.QUOTA_ENDPOINTS)


def test_provider_fetch_models_with_plan(fake_fetch):
    calls = fake_fetch({"/v4/models": "zai_models.json", "/quota/limit": "zai_quota.json"})
    args = argparse.Namespace(models=True, endpoint="cn")
    payload = zai.PROVIDER.fetch("k", args)
    assert payload["plan"] == "lite"
    assert payload["models"]["data"][0]["id"] == "GLM-4.5-Air"
    assert calls == [zai.MODELS_ENDPOINTS["cn"], zai.QUOTA_ENDPOINTS["cn"]]


def test_provider_fetch_models_quota_failure_is_tolerated(fake_fetch):
    fake_fetch({"/v4/models": "zai_models.json", "/quota/limit": core.QuotaError("down")})
    args = argparse.Namespace(models=True, endpoint=None)
    payload = zai.PROVIDER.fetch("k", args)
    assert payload["plan"] == ""


def test_provider_to_json_models_is_merged_list():
    args = argparse.Namespace(models=True)
    payload = {"models": load_fixture("zai_models.json"), "plan": "lite"}
    out = zai.PROVIDER.to_json(payload, args)
    assert isinstance(out, list)
    assert {"id", "object", "created", "source"} <= set(out[0])


def test_provider_metadata():
    assert zai.PROVIDER.name == "zai"
    assert zai.PROVIDER.env_vars == ("ZAI_API_KEY",)
    assert zai.PROVIDER.hermes_pool == "zai"
