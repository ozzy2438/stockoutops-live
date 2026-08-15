PYTHON := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: setup up migrate seed shadow-cases shadow-pilot shadow-intake shadow-exclude shadow-collection alert-pilot alert-webhook-proof serve lint test smoke-stub down docker-build

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

shadow-cases:
	$(PYTHON) -c "from pathlib import Path; from stockoutops.shadow.cases import load_case_pack; loaded = load_case_pack(Path('evaluation/shadow/cases/v1')); print(loaded.pack.case_pack_version, len(loaded.pack.cases))"

shadow-pilot:
	$(PYTHON) -m stockoutops.shadow.cli

shadow-intake:
	$(PYTHON) -m stockoutops.shadow.intake --input $(INPUT) --execute false

shadow-exclude:
	$(PYTHON) -c "from stockoutops.shadow.intake import exclude_main; exclude_main()" --intake-id $(INTAKE_ID) --tenant-id $(TENANT_ID) --reason $(REASON)

shadow-collection:
	$(PYTHON) -m stockoutops.shadow.collection

alert-pilot:
	$(PYTHON) -m stockoutops.alerting.cli

alert-webhook-proof:
	$(PYTHON) -m pytest tests/unit/test_alert_delivery.py tests/integration/test_alert_delivery.py -q

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
