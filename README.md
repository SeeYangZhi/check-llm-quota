# check-llm-quota

Check usage quota, rate limits, remaining sessions and supported models across
LLM API providers from one command. Stdlib only, no dependencies.

Supported providers:

| Provider | Subcommand | What it reports |
|----------|------------|-----------------|
| [Z.ai](https://z.ai) (Zhipu AI / 智谱AI) GLM Coding Plan | `zai` | Plan level, per-limit usage % (time, tokens, sessions, requests), reset times, model availability per plan |
| [Kimi](https://kimi.com) (Moonshot AI) Coding API | `kimi` | Plan, weekly quota, rolling-window rate limit, max parallel requests, model list |

This package merges and replaces the standalone
[zai-quota](https://github.com/SeeYangZhi/zai-quota) and
[kimi-quota](https://github.com/SeeYangZhi/kimi-quota) tools. Both old
command names still work as aliases.

## Quick start

```bash
# Run without installing (uv: https://docs.astral.sh/uv/)
uvx check-llm-quota all

# Or install it
uv tool install check-llm-quota     # or: pip install check-llm-quota
check-llm-quota all
```

```
=== kimi ===
🔑 Kimi Coding API — Quota Report
   Plan: Paid (BASIC)

📋 Weekly Quota:
   Used: 20/100 (20%)
   Remaining: 80
   Resets: 2026-06-21 08:14 SGT

📊 Rate Limit (300minute rolling window):
   Used: 1/100 (1%)
   Remaining: 99
   Resets: 2026-06-17 09:14 SGT

⚡ Max Parallel Requests: 10

=== zai ===
  Z.ai GLM Quota
  Plan: Lite
  -------------------------------------
  [green] Time Limit
     Used: 0% | Remaining: 100
       - search-prime: 0
       - web-reader: 0
       - zread: 0
     Resets: 2026-04-16 10:31 SGT

  [green] Tokens
     Used: 18%
     Resets: in 3h

  -------------------------------------
```

## Usage

```bash
check-llm-quota <provider|all> [--key KEY] [--json] [provider flags]

check-llm-quota zai                   # Z.ai quota report
check-llm-quota zai --models          # GLM models and which plan unlocks them
check-llm-quota zai --endpoint cn     # force open.bigmodel.cn (default: api.z.ai, then cn)
check-llm-quota kimi                  # Kimi quota report
check-llm-quota kimi --models         # Kimi model list
check-llm-quota kimi --base-url URL   # custom Kimi-compatible endpoint
check-llm-quota all                   # every provider with a key configured
check-llm-quota all --json            # {"kimi": {...}, "zai": {...}}
check-llm-quota --json zai            # --key/--json work before or after the provider

python3 -m check_llm_quota all        # module form, same CLI
zai-quota --models                    # alias for: check-llm-quota zai --models
kimi-quota --json                     # alias for: check-llm-quota kimi --json
```

Exit codes: `0` success, `1` missing key or API failure (with `all`, 1 if any
provider failed), `2` invalid arguments.

## API keys per provider

Resolution order is always `--key` > environment variables > provider fallback.

### zai

| Source | Notes |
|--------|-------|
| `--key` | |
| `ZAI_API_KEY` | from [z.ai](https://z.ai) or [open.bigmodel.cn](https://open.bigmodel.cn) |
| `~/.hermes/auth.json` | [Hermes Agent](https://hermes-agent.nousresearch.com/) credential pool: first entry of `credential_pool.zai[]` with a non-empty `access_token` (a legacy top-level `zai: [...]` list is also read) |

The quota endpoint is an unofficial monitoring API (`/api/monitor/usage/quota/limit`).
It works today but Z.ai could change it without notice. `api.z.ai` is tried
first and `open.bigmodel.cn` second; pass `--endpoint intl|cn` to pin one.

### kimi

| Source | Notes |
|--------|-------|
| `--key` | |
| `MOONSHOT_API_KEY` | checked first |
| `KIMI_API_KEY` | checked second |
| `KIMI_BASE_URL` / `--base-url` | override `https://api.kimi.com/coding/v1` |

### all

`all` only uses environment variables and the Hermes file. Providers without a
key are skipped with a note on stderr, and one provider failing does not stop
the others. `--key` is rejected because it is ambiguous across providers.

## Cron example

Log a JSON snapshot every hour and warn in the system log when any provider fails:

```cron
# m h dom mon dow   command
0 * * * *  ZAI_API_KEY=... MOONSHOT_API_KEY=... /usr/local/bin/uvx check-llm-quota all --json >> "$HOME/llm-quota.log" 2>&1 || logger -t check-llm-quota "quota check failed"
```

Set the keys in the crontab (as above), in a sourced env file, or rely on
`~/.hermes/auth.json` for Z.ai. Use the absolute path to `uvx` (`which uvx`)
since cron has a minimal `PATH`. For a plain-text daily report, drop `--json`
and pipe to `mail` or your notifier of choice.

## Agent skill

The repository is also an [Agent Skills](https://skills.sh) bundle. Install
into Claude Code, Codex, Cursor, OpenCode, Gemini CLI, Hermes and 45+ other agents:

```bash
npx skills add SeeYangZhi/check-llm-quota
```

Three skills are provided:

- `check-llm-quota`: the full multi-provider skill. Its `scripts/check_quota.py`
  is a thin dispatcher that runs `uvx check-llm-quota <args>` and falls back
  to `python3 -m check_llm_quota <args>`.
- `zai-quota` and `kimi-quota`: short pointer skills so prompts such as
  "check my GLM quota" or "how much Kimi usage is left" still trigger.

Agents run, for example:

```bash
python3 skills/check-llm-quota/scripts/check_quota.py all
```

## Adding a provider

Each provider is one file in `src/check_llm_quota/providers/`. The registry
imports every module there and picks up any module-level `PROVIDER` that is a
`check_llm_quota.core.Provider` instance, so there is nothing else to wire up.

1. Create `src/check_llm_quota/providers/<name>.py`:

   ```python
   import argparse
   from typing import Any

   from .. import core
   from ..core import Provider, fmt_sgt, pct, pct_status


   class ExampleProvider(Provider):
       name = "example"                      # subcommand name
       description = "Example AI usage and limits"
       env_vars = ("EXAMPLE_API_KEY",)       # checked in order
       hermes_pool = None                    # or a ~/.hermes/auth.json pool name
       missing_key_message = "No Example key. Set EXAMPLE_API_KEY or pass --key."

       def add_arguments(self, parser: argparse.ArgumentParser) -> None:
           # --key and --json are added for you
           parser.add_argument("--models", action="store_true", help="List models")

       def fetch(self, key: str, args: argparse.Namespace) -> Any:
           # Raise core.QuotaError for user-facing failures; never sys.exit.
           return core.fetch_json("https://api.example.com/v1/usage", key, label="Example")

       def render(self, payload: Any, args: argparse.Namespace) -> None:
           used, total = payload["used"], payload["limit"]
           print(f"[{pct_status(pct(used, total))}] Used {used}/{total} ({pct(used, total)}%)")
           print(f"Resets: {fmt_sgt(payload['resetTime'])}")

       # Optional: shape what --json prints (defaults to the raw payload).
       # def to_json(self, payload, args): ...


   PROVIDER = ExampleProvider()
   ```

2. Helpers in `core` you can reuse: `fetch_json` (Bearer auth, multi-URL
   fallback on 404/connection errors, 401 fails fast), `resolve_key`,
   `hermes_pool_key`, `format_reset` (ms epoch to relative/SGT), `fmt_sgt`
   (ISO UTC to SGT), `pct`, `pct_status`.

3. Add fixture JSON under `tests/fixtures/` and tests next to the existing
   `tests/test_zai.py` / `tests/test_kimi.py`. Tests are offline: `conftest.py`
   blocks `urllib` and provides `fake_fetch` to map URL substrings to fixtures.

4. Document the env vars in this README and, if useful, add a pointer skill in
   `skills/<name>-quota/SKILL.md`.

## Development

```bash
uv run pytest        # offline test suite  (make test)
make check           # --help smoke test for every entry point
uv build             # wheel + sdist       (make build)
```

Requires Python 3.9+. CI runs the tests on 3.9, 3.12 and 3.13.

## License

MIT
