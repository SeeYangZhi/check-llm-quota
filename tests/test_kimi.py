"""Renderer tests for the Kimi provider, driven by fixture JSON."""

from __future__ import annotations

import argparse

from check_llm_quota.providers import kimi

from conftest import load_fixture


def test_get_base_url(monkeypatch):
    assert kimi.get_base_url() == "https://api.kimi.com/coding/v1"
    monkeypatch.setenv("KIMI_BASE_URL", "https://proxy.example/v1/")
    assert kimi.get_base_url() == "https://proxy.example/v1"
    assert kimi.get_base_url("https://cli.example/") == "https://cli.example"


def test_print_quota_paid(capsys):
    kimi.print_quota(load_fixture("kimi_usages.json"))
    out = capsys.readouterr().out
    expected = (
        "🔑 Kimi Coding API — Quota Report\n"
        "   Plan: Paid (BASIC)\n"
        "\n"
        "📋 Weekly Quota:\n"
        "   Used: 20/100 (20%)\n"
        "   Remaining: 80\n"
        "   Resets: 2026-06-21 08:14 SGT\n"
        "\n"
        "📊 Rate Limit (300minute rolling window):\n"
        "   Used: 1/100 (1%)\n"
        "   Remaining: 99\n"
        "   Resets: 2026-06-17 09:14 SGT\n"
        "\n"
        "⚡ Max Parallel Requests: 10\n"
    )
    assert out == expected


def test_print_quota_free_low_warning(capsys):
    kimi.print_quota(load_fixture("kimi_usages_low.json"))
    out = capsys.readouterr().out
    assert "Plan: Free (FREE)" in out
    assert "Used: 45/50 (90%)" in out
    assert "Rate Limit" not in out
    assert "Max Parallel Requests: 2" in out
    assert "⚠️  Low quota: only 5/50 remaining (90% used)!" in out


def test_print_quota_empty_payload(capsys):
    kimi.print_quota({})
    out = capsys.readouterr().out
    assert "Plan: Free (unknown)" in out
    assert "Used: 0/0 (0%)" in out
    assert "Max Parallel Requests: ?" in out
    assert "Low quota" not in out


def test_print_models(capsys):
    kimi.print_models(load_fixture("kimi_models.json"))
    out = capsys.readouterr().out
    assert "🤖 Available Models (2):" in out
    assert "   • kimi-k2-0905-preview (by moonshot)" in out
    assert "   • kimi-k2-turbo-preview (by moonshot)" in out


def test_print_models_empty(capsys):
    kimi.print_models({"data": []})
    assert capsys.readouterr().out == "No models found.\n"


def test_provider_fetch_usages_url(fake_fetch):
    calls = fake_fetch({"/usages": "kimi_usages.json"})
    args = argparse.Namespace(models=False, base_url=None)
    payload = kimi.PROVIDER.fetch("k", args)
    assert payload["subType"] == "TYPE_PURCHASE"
    assert calls == ["https://api.kimi.com/coding/v1/usages"]


def test_provider_fetch_models_custom_base_url(fake_fetch):
    calls = fake_fetch({"/models": "kimi_models.json"})
    args = argparse.Namespace(models=True, base_url="https://proxy.example/v1/")
    kimi.PROVIDER.fetch("k", args)
    assert calls == ["https://proxy.example/v1/models"]


def test_provider_metadata():
    assert kimi.PROVIDER.name == "kimi"
    assert kimi.PROVIDER.env_vars == ("MOONSHOT_API_KEY", "KIMI_API_KEY")
    assert kimi.PROVIDER.hermes_pool is None
    assert kimi.PROVIDER.to_json({"x": 1}, argparse.Namespace()) == {"x": 1}
