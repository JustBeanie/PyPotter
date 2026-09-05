install:
	uv sync --extra dev

check:
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy pypotter
	uv run pytest --cov

frontend:
	cd frontend && pnpm install --frozen-lockfile && pnpm run build
