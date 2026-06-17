# Helix — common developer tasks. (Targets are illustrative during pre-alpha scaffolding.)

.PHONY: help sync test lint fmt typecheck check cli mcp dashboard clean

help:           ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

sync:           ## Install the Python workspace (uv)
	uv sync

test:           ## Run the test suite (incl. the $0/offline path)
	uv run pytest --cov

lint:           ## Lint Python
	uv run ruff check .

fmt:            ## Format Python
	uv run black .
	uv run ruff check --fix .

typecheck:      ## Type-check Python
	uv run mypy packages

check: lint typecheck test   ## All gates (run before committing)

cli:            ## Smoke-test the CLI
	uv run helix --help

mcp:            ## Run the MCP server (stdio)
	uv run helix-mcp serve --stdio

dashboard:      ## Run the local dashboard (TS)
	pnpm -C apps/dashboard dev

clean:          ## Remove caches/build artifacts
	rm -rf .ruff_cache .mypy_cache .pytest_cache **/__pycache__ **/dist **/build
