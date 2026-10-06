"""Command-line interface: ``check-llm-quota <provider|all> [flags]``.

Also exposes :func:`zai_main` and :func:`kimi_main`, the entrypoints behind
the back-compat ``zai-quota`` / ``kimi-quota`` console scripts.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

from . import __version__
from .core import Provider, QuotaError
from .providers import get_providers

PROG = "check-llm-quota"
ALL = "all"


def _eprint(*parts: Any) -> None:
    print(*parts, file=sys.stderr)


def _add_common_flags(parser: argparse.ArgumentParser, *, suppress: bool) -> None:
    """``--key`` / ``--json`` are accepted both before and after the subcommand.

    The subparser copies use ``argparse.SUPPRESS`` defaults so they only
    override the top-level value when actually given.
    """
    parser.add_argument(
        "--key", "-k",
        default=argparse.SUPPRESS if suppress else None,
        help="API key (overrides provider env vars / Hermes auth.json)",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        default=argparse.SUPPRESS if suppress else False,
        help="Output raw JSON instead of a report",
    )


def build_parser(providers: Dict[str, Provider]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Check usage quota and limits across LLM API providers.",
        epilog="Run '%(prog)s <provider> --help' for provider-specific flags.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    _add_common_flags(parser, suppress=False)

    sub = parser.add_subparsers(dest="provider", metavar="PROVIDER", required=True)
    for name, provider in providers.items():
        sp = sub.add_parser(name, help=provider.description, description=provider.description)
        _add_common_flags(sp, suppress=True)
        provider.add_arguments(sp)

    sp_all = sub.add_parser(
        ALL,
        help="Check every provider that has an API key configured",
        description=(
            "Run every provider whose API key is configured via environment "
            "variables (or Hermes auth.json). Providers are isolated: one "
            "failing does not stop the others. Exit status is 1 if any failed."
        ),
    )
    _add_common_flags(sp_all, suppress=True)
    return parser


def run_provider(provider: Provider, key: str, args: argparse.Namespace) -> None:
    """Fetch and print one provider. Raises :class:`QuotaError` on failure."""
    payload = provider.fetch(key, args)
    if args.json:
        print(json.dumps(provider.to_json(payload, args), indent=2))
    else:
        provider.render(payload, args)


def run_all(providers: Dict[str, Provider], args: argparse.Namespace) -> int:
    if args.key:
        _eprint("--key cannot be combined with 'all'; set each provider's env var instead.")
        return 1

    configured = {name: p for name, p in providers.items() if p.is_configured()}
    for name, p in providers.items():
        if name not in configured:
            _eprint(f"[{name}] skipped: no API key configured ({', '.join(p.env_vars)})")

    if not configured:
        hints = ", ".join(v for p in providers.values() for v in p.env_vars)
        _eprint(f"No provider API keys configured. Set one of: {hints}")
        return 1

    failures = 0
    results: Dict[str, Any] = {}
    first = True
    for name, provider in configured.items():
        key = provider.resolve_key(None)
        try:
            payload = provider.fetch(key or "", args)
        except QuotaError as e:
            failures += 1
            _eprint(f"[{name}] {e}")
            results[name] = {"error": str(e)}
            continue
        except Exception as e:  # keep one provider's bug from hiding the others
            failures += 1
            _eprint(f"[{name}] unexpected error: {type(e).__name__}: {e}")
            results[name] = {"error": f"{type(e).__name__}: {e}"}
            continue

        if args.json:
            results[name] = provider.to_json(payload, args)
        else:
            if not first:
                print()
            first = False
            print(f"=== {name} ===")
            provider.render(payload, args)

    if args.json:
        print(json.dumps(results, indent=2))

    return 1 if failures else 0


def main(argv: Optional[List[str]] = None) -> int:
    providers = get_providers()
    parser = build_parser(providers)
    args = parser.parse_args(argv)

    if args.provider == ALL:
        return run_all(providers, args)

    provider = providers[args.provider]
    key = provider.resolve_key(args.key)
    if not key:
        _eprint(provider.missing_key_message)
        return 1

    try:
        run_provider(provider, key, args)
    except QuotaError as e:
        _eprint(str(e))
        return 1
    return 0


def _alias_main(provider_name: str, argv: Optional[List[str]]) -> int:
    rest = list(sys.argv[1:]) if argv is None else list(argv)
    return main([provider_name, *rest])


def zai_main(argv: Optional[List[str]] = None) -> int:
    """Entry point for the back-compat ``zai-quota`` console script."""
    return _alias_main("zai", argv)


def kimi_main(argv: Optional[List[str]] = None) -> int:
    """Entry point for the back-compat ``kimi-quota`` console script."""
    return _alias_main("kimi", argv)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
