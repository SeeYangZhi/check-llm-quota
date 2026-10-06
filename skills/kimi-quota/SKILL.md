---
name: kimi-quota
description: Check Kimi (Moonshot AI) Coding API quota, weekly usage, rate limits, parallel request limits and available models. Use when the user asks about kimi quota, moonshot quota, coding plan usage, or Kimi API limits.
license: MIT
compatibility: Requires Python 3.9+ and internet access to api.kimi.com. Uses the check-llm-quota package via uvx.
metadata:
  author: Yang Zhi See
  version: "2.0.0"
  repository: https://github.com/SeeYangZhi/check-llm-quota
---

# Kimi Quota Check

This skill is a pointer to the `check-llm-quota` skill in the same
repository. Everything runs through its dispatcher with the `kimi` subcommand.

## How to Run

```bash
python3 skills/check-llm-quota/scripts/check_quota.py kimi
python3 skills/check-llm-quota/scripts/check_quota.py kimi --models
python3 skills/check-llm-quota/scripts/check_quota.py kimi --json
```

Or directly: `uvx check-llm-quota kimi` (alias: `uvx --from check-llm-quota kimi-quota`).

## API Key Resolution (in priority order)

1. `--key` CLI argument
2. `MOONSHOT_API_KEY`, then `KIMI_API_KEY` environment variable

`KIMI_BASE_URL` (or `--base-url`) overrides the default
`https://api.kimi.com/coding/v1`.

See `skills/check-llm-quota/SKILL.md` for flags, output format and exit codes.
