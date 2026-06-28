# GHOSTWIRE backend verify-loop entrypoint.
# `make verify` runs the tier-1 deterministic gate (no docker required). Docker-dependent
# bring-up (migrate + seed + smoke) is separate (`make up`, `make migrate`, `make seed`).

VENV := .venv
PY := $(VENV)/bin/python
RUFF := $(VENV)/bin/ruff
MYPY := $(VENV)/bin/mypy
UVICORN := $(VENV)/bin/uvicorn
ALEMBIC := $(VENV)/bin/alembic
REPO_ROOT := $(shell cd .. && pwd)

.PHONY: verify tier1 compile lint typecheck contract boot install up down migrate seed smoke

verify: tier1

## --- Tier 1: deterministic gate (cheapest first; stop at first failure) ---
tier1: compile lint typecheck contract boot
	@echo "TIER-1 GREEN"

compile:
	@echo "== compile / import-check =="
	$(PY) -m py_compile $(shell find app -name '*.py' -not -path '*/migrations/*')
	$(PY) -c "import app.contracts, app.config, app.main, app.db, app.shared_security, app.knowledge_core; print('imports OK')"

lint:
	@echo "== ruff check + format --check =="
	$(RUFF) check app tests
	$(RUFF) format --check app tests

typecheck:
	@echo "== mypy =="
	$(MYPY) app

contract:
	@echo "== contract-validate (jsonschema) + no-redefine assertion =="
	$(PY) $(REPO_ROOT)/system/scripts/validate_contracts.py $(REPO_ROOT)
	$(PY) -m tests.assert_frozen_types

boot:
	@echo "== boot-import (uvicorn app imports cleanly) =="
	$(PY) -c "from app.main import app; assert app.title == 'GHOSTWIRE API'; print('boot-import OK')"

## --- Docker-dependent (best effort) ---
install:
	python3 -m uv pip install --python $(PY) -e ".[dev]"

up:
	cd $(REPO_ROOT) && docker compose up -d

down:
	cd $(REPO_ROOT) && docker compose down

migrate:
	$(ALEMBIC) upgrade head

seed:
	$(PY) -m app.knowledge_core.ingest

smoke:
	$(PY) -m tests.smoke
