.PHONY: sync test lint download aggregate site pipeline all

sync:
	uv sync

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check .

download:
	uv run python scripts/download.py

aggregate:
	uv run python scripts/aggregate.py

site:
	uv run python scripts/generate_site.py

pipeline: download aggregate site

all: sync test pipeline
