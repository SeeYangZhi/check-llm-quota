.PHONY: help test check build publish clean

help:
	@echo "Available targets:"
	@echo "  test     - Run the offline test suite with uv + pytest"
	@echo "  check    - Smoke-test every console script and the skill dispatcher (--help)"
	@echo "  build    - Build wheel and sdist with uv"
	@echo "  publish  - Build and publish to PyPI with uv"
	@echo "  clean    - Remove build artefacts and caches"

test:
	uv run pytest

check:
	uv run check-llm-quota --help
	uv run check-llm-quota zai --help
	uv run check-llm-quota kimi --help
	uv run zai-quota --help
	uv run kimi-quota --help
	uv run python skills/check-llm-quota/scripts/check_quota.py --help

build:
	uv build

publish:
	uv build
	uv publish

clean:
	rm -rf dist build .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
