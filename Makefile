PYTHON := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: setup up migrate seed serve lint test smoke-stub down docker-build

setup:
	python3.12 -m venv .venv
	$(PIP) install -e ".[test]"
	$(PYTHON) scripts/create_local_identities.py

up:
	docker compose up -d --build

migrate:
	$(PYTHON) -m stockoutops.database

seed:
	$(PYTHON) -m stockoutops.evidence.seed

serve:
	$(PYTHON) -m uvicorn stockoutops.app:create_app --factory --host 127.0.0.1 --port 8000

lint:
	$(PYTHON) -m ruff format --check .
	$(PYTHON) -m ruff check .

test:
	$(PYTHON) -m pytest

smoke-stub:
	$(PYTHON) -m stockoutops.smoke

docker-build:
	docker build -t stockoutops-live:m1-local .

down:
	docker compose down
