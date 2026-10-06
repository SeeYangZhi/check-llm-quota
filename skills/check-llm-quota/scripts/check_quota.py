#!/usr/bin/env python3
"""Thin dispatcher for the check-llm-quota agent skill.

Forwards every argument to the ``check-llm-quota`` CLI. Resolution order:

1. A local checkout or an installed package: if ``check_llm_quota`` is
   importable (the repo's ``src/`` is added to ``sys.path`` when present),
   run it in-process. No network needed to start.
2. ``uvx check-llm-quota <args>`` when ``uvx`` is on PATH (fetches the
   published package on first use and caches it).
3. ``python3 -m check_llm_quota <args>`` as a last resort, which works when
   the package was ``pip install``-ed into that interpreter.

Examples:
    python3 skills/check-llm-quota/scripts/check_quota.py zai
    python3 skills/check-llm-quota/scripts/check_quota.py kimi --models
    python3 skills/check-llm-quota/scripts/check_quota.py all --json
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PACKAGE = "check_llm_quota"
DIST = "check-llm-quota"


def _local_src() -> Path | None:
    # <repo>/skills/check-llm-quota/scripts/check_quota.py -> <repo>/src
    src = Path(__file__).resolve().parents[3] / "src"
    return src if (src / PACKAGE / "cli.py").is_file() else None


def _run_in_process(argv: list[str]) -> int:
    src = _local_src()
    if src is not None and str(src) not in sys.path:
        sys.path.insert(0, str(src))
    try:
        from check_llm_quota.cli import main
    except ImportError:
        return -1
    return int(main(argv) or 0)


def _run_subprocess(cmd: list[str]) -> int:
    try:
        return subprocess.call(cmd)
    except OSError as e:  # binary vanished between lookup and exec, etc.
        print(f"check-llm-quota: failed to run {cmd[0]}: {e}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:]) if argv is None else list(argv)

    rc = _run_in_process(args)
    if rc != -1:
        return rc

    uvx = shutil.which("uvx")
    if uvx and not os.environ.get("CHECK_LLM_QUOTA_NO_UVX"):
        return _run_subprocess([uvx, DIST, *args])

    python = sys.executable or shutil.which("python3") or "python3"
    rc = _run_subprocess([python, "-m", PACKAGE, *args])
    if rc != 0:
        print(
            f"check-llm-quota: not installed. Run 'uvx {DIST} ...' "
            f"(install uv from https://docs.astral.sh/uv/) or 'pip install {DIST}'.",
            file=sys.stderr,
        )
    return rc


if __name__ == "__main__":
    sys.exit(main())
