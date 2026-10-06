---
name: zai-quota
description: Check Z.ai (Zhipu AI) GLM API usage quota, remaining sessions, token limits and supported models. Use when the user asks about zai quota, GLM quota, Zhipu API usage, or remaining sessions for Z.ai.
license: MIT
compatibility: Requires Python 3.9+ and internet access to api.z.ai or open.bigmodel.cn. Uses the check-llm-quota package via uvx.
metadata:
  author: Yang Zhi See
  version: "2.0.0"
  repository: https://github.com/SeeYangZhi/check-llm-quota
---

# Z.ai GLM Quota Check

This skill is a pointer to the `check-llm-quota` skill in the same
repository. Everything runs through its dispatcher with the `zai` subcommand.

## How to Run

```bash
python3 skills/check-llm-quota/scripts/check_quota.py zai
python3 skills/check-llm-quota/scripts/check_quota.py zai --models
python3 skills/check-llm-quota/scripts/check_quota.py zai --json
python3 skills/check-llm-quota/scripts/check_quota.py zai --endpoint cn
```

Or directly: `uvx check-llm-quota zai` (alias: `uvx --from check-llm-quota zai-quota`).

## API Key Resolution (in priority order)

1. `--key` CLI argument
2. `ZAI_API_KEY` environment variable
3. `~/.hermes/auth.json` (Hermes Agent credential pool `zai`)

See `skills/check-llm-quota/SKILL.md` for flags, output format and exit codes.
