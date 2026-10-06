---
name: check-llm-quota
description: Check usage quota, rate limits, remaining sessions and supported models across LLM API providers (Z.ai/Zhipu GLM Coding Plan, Kimi/Moonshot Coding API). Use when the user asks about their LLM API quota, remaining usage, rate limits, or which providers still have budget left.
license: MIT
compatibility: Requires Python 3.9+ and internet access to the provider APIs. Works with uvx (recommended) or a pip-installed check-llm-quota package.
metadata:
  author: Yang Zhi See
  version: "0.1.0"
  repository: https://github.com/SeeYangZhi/check-llm-quota
---

# check-llm-quota

One CLI that reports remaining quota for several LLM API providers. The
dispatcher script forwards all arguments to the `check-llm-quota` CLI and
runs it via `uvx check-llm-quota` (falling back to `python3 -m check_llm_quota`).

## How to Run

```bash
# All providers that have an API key configured
python3 skills/check-llm-quota/scripts/check_quota.py all

# A single provider
python3 skills/check-llm-quota/scripts/check_quota.py zai
python3 skills/check-llm-quota/scripts/check_quota.py kimi

# Raw JSON (works before or after the provider name)
python3 skills/check-llm-quota/scripts/check_quota.py all --json
python3 skills/check-llm-quota/scripts/check_quota.py --json zai

# Supported models
python3 skills/check-llm-quota/scripts/check_quota.py zai --models
python3 skills/check-llm-quota/scripts/check_quota.py kimi --models
```

Equivalent direct invocations if the tool is installed:

```bash
uvx check-llm-quota all
check-llm-quota zai --models
zai-quota          # back-compat alias for: check-llm-quota zai
kimi-quota         # back-compat alias for: check-llm-quota kimi
```

## Providers and API Key Resolution

Priority is always `--key` > environment variables > provider-specific fallback.

| Provider | Subcommand | Environment variables | Extra fallback |
|----------|------------|-----------------------|----------------|
| Z.ai (Zhipu AI) GLM Coding Plan | `zai` | `ZAI_API_KEY` | `~/.hermes/auth.json` credential pool `zai` |
| Kimi (Moonshot AI) Coding API | `kimi` | `MOONSHOT_API_KEY`, then `KIMI_API_KEY` | `KIMI_BASE_URL` overrides the API base URL |

`all` runs every provider that has a key configured, skips the others with a
note on stderr, and exits 1 if any provider failed. `--key` is not allowed
with `all`.

## Provider Flags

```bash
# zai
--models, -m           List supported GLM models and which plan unlocks them
--endpoint {intl,cn}   Force api.z.ai (intl) or open.bigmodel.cn (cn); default tries intl then cn

# kimi
--models               List available models
--base-url URL         Override https://api.kimi.com/coding/v1
```

## Interpreting Output

- Z.ai: each limit line is tagged `[green]` (<50% used), `[yellow]` (<80%) or `[red]`. "Resets" is relative when under 24h, otherwise an SGT timestamp.
- Kimi: weekly quota, rolling-window rate limit and max parallel requests. A `⚠️ Low quota` warning appears under 20% remaining.
- Exit code 0 on success, 1 on a missing key or API failure, 2 on bad arguments.

## Related Skills

`zai-quota` and `kimi-quota` in this repository are thin pointers to this
skill for users who only care about one provider.
