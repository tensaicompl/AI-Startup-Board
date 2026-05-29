.PHONY: install test lint type cov clean run-example ab-example

install:
	uv sync --all-extras || pip install -e ".[dev]"

test:
	pytest

cov:
	pytest --cov=sboard --cov-report=html --cov-report=term-missing

lint:
	ruff check src tests

type:
	mypy --strict src

check: lint type test

clean:
	rm -rf build/ dist/ *.egg-info htmlcov/ .coverage .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +

run-example:
	sboard convene tests/fixtures/petitions/01-iso-compliance.json

ab-example:
	sboard ab tests/fixtures/petitions/01-iso-compliance.json
