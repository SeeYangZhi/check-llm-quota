"""CLI dispatch tests: subcommands, aliases, ``all``, flag placement, exit codes."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from check_llm_quota import __version__, cli
from check_llm_quota.core import QuotaError
from check_llm_quota.providers import get_providers

from conftest import FIXTURES

ROOT = Path(__file__).resolve().parents[1]
DISPATCHER = ROOT / "skills" / "check-llm-quota" / "scripts" / "check_quota.py"

ZAI_ROUTES = {"/quota/limit": "zai_quota.json", "/v4/models": "zai_models.json"}
KIMI_ROUTES = {"/usages": "kimi_usages.json", "/models": "kimi_models.json"}


def test_registry_discovers_both_providers():
    assert list(get_providers()) == ["kimi", "zai"]


def test_version(capsys):
    with pytest.raises(SystemExit) as ei:
        cli.main(["--version"])
    assert ei.value.code == 0
    assert f"check-llm-quota {__version__}" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [[], ["--help"], ["zai", "--help"], ["kimi", "--help"], ["all", "--help"]])
def test_help_and_no_args(argv, capsys):
    with pytest.raises(SystemExit) as ei:
        cli.main(argv)
    captured = capsys.readouterr()
    if argv:
        assert ei.value.code == 0
        assert "usage: check-llm-quota" in captured.out
    else:
        assert ei.value.code == 2
        assert "required" in captured.err


def test_help_lists_provider_descriptions(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    assert "zai" in out and "kimi" in out and "all" in out
    assert "Z.ai (Zhipu AI)" in out
    assert "Kimi (Moonshot AI)" in out


def test_zai_missing_key(capsys):
    assert cli.main(["zai"]) == 1
    err = capsys.readouterr().err
    assert "No Z.ai API key found" in err
    assert "ZAI_API_KEY" in err


def test_kimi_missing_key(capsys):
    assert cli.main(["kimi"]) == 1
    assert "MOONSHOT_API_KEY or KIMI_API_KEY" in capsys.readouterr().err


def test_zai_report_with_env_key(fake_fetch, monkeypatch, capsys):
    monkeypatch.setenv("ZAI_API_KEY", "env-key")
    fake_fetch(ZAI_ROUTES)
    assert cli.main(["zai"]) == 0
    out = capsys.readouterr().out
    assert "Z.ai GLM Quota" in out
    assert "Plan: Lite" in out


def test_zai_key_from_hermes_pool(fake_fetch, monkeypatch, capsys):
    from check_llm_quota import core

    monkeypatch.setattr(core, "hermes_auth_path", lambda: FIXTURES / "hermes_auth.json")
    seen_keys = []

    def _fetch(urls, api_key, **kw):
        seen_keys.append(api_key)
        return {"data": {"level": "lite", "limits": []}}

    monkeypatch.setattr(core, "fetch_json", _fetch)
    assert cli.main(["zai"]) == 0
    assert seen_keys == ["pool-token-zai"]


def test_zai_json_flag_before_or_after_subcommand(fake_fetch, capsys):
    fake_fetch(ZAI_ROUTES)
    assert cli.main(["--json", "zai", "--key", "k"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert cli.main(["zai", "--key", "k", "--json"]) == 0
    second = json.loads(capsys.readouterr().out)
    assert first == second
    assert first["data"]["level"] == "lite"


def test_zai_models_json_is_merged_list(fake_fetch, capsys):
    fake_fetch(ZAI_ROUTES)
    assert cli.main(["zai", "-k", "k", "-m", "-j"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list)
    assert any(m["id"] == "GLM-4.6" and m["source"] == "api" for m in data)
    assert any(m["source"] == "plan" for m in data)


def test_zai_endpoint_flag_routes_cn_only(fake_fetch, capsys):
    calls = fake_fetch(ZAI_ROUTES)
    assert cli.main(["zai", "--key", "k", "--endpoint", "cn"]) == 0
    assert calls == ["https://open.bigmodel.cn/api/monitor/usage/quota/limit"]


def test_zai_bad_endpoint_choice(capsys):
    with pytest.raises(SystemExit) as ei:
        cli.main(["zai", "--key", "k", "--endpoint", "mars"])
    assert ei.value.code == 2


def test_kimi_report(fake_fetch, monkeypatch, capsys):
    monkeypatch.setenv("KIMI_API_KEY", "kk")
    fake_fetch(KIMI_ROUTES)
    assert cli.main(["kimi"]) == 0
    out = capsys.readouterr().out
    assert "Kimi Coding API" in out
    assert "Used: 20/100 (20%)" in out


def test_kimi_models_json_passthrough(fake_fetch, capsys):
    fake_fetch(KIMI_ROUTES)
    assert cli.main(["kimi", "--key", "k", "--models", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["data"][0]["id"] == "kimi-k2-0905-preview"


def test_kimi_base_url_flag(fake_fetch, capsys):
    calls = fake_fetch(KIMI_ROUTES)
    assert cli.main(["kimi", "--key", "k", "--base-url", "https://proxy.example/v1"]) == 0
    assert calls == ["https://proxy.example/v1/usages"]


def test_quota_error_is_reported_with_exit_1(fake_fetch, capsys):
    fake_fetch({"/usages": QuotaError("HTTP 500: boom")})
    assert cli.main(["kimi", "--key", "k"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "HTTP 500: boom" in captured.err


# --- back-compat aliases ---------------------------------------------------


def test_zai_alias(fake_fetch, capsys):
    fake_fetch(ZAI_ROUTES)
    assert cli.zai_main(["--key", "k", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["level"] == "lite"


def test_kimi_alias(fake_fetch, capsys):
    fake_fetch(KIMI_ROUTES)
    assert cli.kimi_main(["--key", "k"]) == 0
    assert "Kimi Coding API" in capsys.readouterr().out


def test_alias_uses_sys_argv_when_argv_none(fake_fetch, monkeypatch, capsys):
    fake_fetch(KIMI_ROUTES)
    monkeypatch.setattr(sys, "argv", ["kimi-quota", "--key", "k", "--models"])
    assert cli.kimi_main() == 0
    assert "Available Models (2)" in capsys.readouterr().out


def test_alias_help_shows_provider_flags(capsys):
    with pytest.raises(SystemExit) as ei:
        cli.zai_main(["--help"])
    assert ei.value.code == 0
    out = capsys.readouterr().out
    assert "--endpoint" in out and "--models" in out


# --- all -------------------------------------------------------------------


def test_all_without_any_keys(capsys):
    assert cli.main(["all"]) == 1
    err = capsys.readouterr().err
    assert "[kimi] skipped" in err
    assert "[zai] skipped" in err
    assert "No provider API keys configured" in err


def test_all_rejects_key_flag(capsys):
    assert cli.main(["all", "--key", "k"]) == 1
    assert "--key cannot be combined with 'all'" in capsys.readouterr().err


def test_all_runs_configured_providers_in_order(fake_fetch, monkeypatch, capsys):
    monkeypatch.setenv("ZAI_API_KEY", "z")
    monkeypatch.setenv("MOONSHOT_API_KEY", "m")
    fake_fetch({**ZAI_ROUTES, **KIMI_ROUTES})
    assert cli.main(["all"]) == 0
    out = capsys.readouterr().out
    assert out.index("=== kimi ===") < out.index("=== zai ===")
    assert "Kimi Coding API" in out
    assert "Z.ai GLM Quota" in out


def test_all_skips_unconfigured_and_reports_them(fake_fetch, monkeypatch, capsys):
    monkeypatch.setenv("ZAI_API_KEY", "z")
    fake_fetch(ZAI_ROUTES)
    assert cli.main(["all"]) == 0
    captured = capsys.readouterr()
    assert "[kimi] skipped: no API key configured (MOONSHOT_API_KEY, KIMI_API_KEY)" in captured.err
    assert "=== zai ===" in captured.out
    assert "=== kimi ===" not in captured.out


def test_all_json_combines_and_isolates_failures(fake_fetch, monkeypatch, capsys):
    monkeypatch.setenv("ZAI_API_KEY", "z")
    monkeypatch.setenv("KIMI_API_KEY", "m")
    fake_fetch({**ZAI_ROUTES, "/usages": QuotaError("HTTP 503: down")})
    assert cli.main(["all", "--json"]) == 1
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["kimi"] == {"error": "HTTP 503: down"}
    assert data["zai"]["data"]["level"] == "lite"
    assert "[kimi] HTTP 503: down" in captured.err


def test_all_isolates_unexpected_exceptions(monkeypatch, capsys):
    from check_llm_quota import core

    monkeypatch.setenv("ZAI_API_KEY", "z")
    monkeypatch.setenv("KIMI_API_KEY", "m")

    def _fetch(urls, api_key, **kw):
        if "usages" in str(urls):
            raise RuntimeError("bug")
        return {"data": {"level": "lite", "limits": []}}

    monkeypatch.setattr(core, "fetch_json", _fetch)
    assert cli.main(["all"]) == 1
    captured = capsys.readouterr()
    assert "[kimi] unexpected error: RuntimeError: bug" in captured.err
    assert "=== zai ===" in captured.out


# --- python -m and skill dispatcher (subprocess, offline --help only) --------


def _run(args, env_extra=None):
    import os

    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    for var in ("ZAI_API_KEY", "MOONSHOT_API_KEY", "KIMI_API_KEY"):
        env.pop(var, None)
    env.update(env_extra or {})
    return subprocess.run(args, capture_output=True, text=True, env=env, timeout=60)


def test_python_m_entry():
    r = _run([sys.executable, "-m", "check_llm_quota", "--help"])
    assert r.returncode == 0, r.stderr
    assert "usage: check-llm-quota" in r.stdout


def test_skill_dispatcher_help():
    r = _run([sys.executable, str(DISPATCHER), "--help"])
    assert r.returncode == 0, r.stderr
    assert "usage: check-llm-quota" in r.stdout


def test_skill_dispatcher_passes_args_and_exit_code(tmp_path):
    # HOME is a scratch dir so no real ~/.hermes/auth.json can supply a key.
    r = _run([sys.executable, str(DISPATCHER), "zai"], env_extra={"HOME": str(tmp_path)})
    assert r.returncode == 1
    assert "No Z.ai API key found" in r.stderr
