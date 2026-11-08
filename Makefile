# Usage: make install | make lint | make test | make ingest | make silver | make gold | make all
PYTHON ?= .venv/bin/python
BOOTSTRAP_PYTHON ?= /opt/anaconda3/bin/python
# macOS can hide the editable-install .pth under iCloud-synced Desktop, so set this explicitly.
export PYTHONPATH := $(CURDIR)
SEASONS ?= 2023-2026

.PHONY: install lint format test ingest ingest-jolpica ingest-openf1 silver gold all

install:
	# .nosync keeps these out of iCloud, which offloads files and makes reads hang.
	mkdir -p data.nosync
	ln -sfn data.nosync data
	$(BOOTSTRAP_PYTHON) -m venv .venv.nosync
	ln -sfn .venv.nosync .venv
	$(PYTHON) -m pip install --quiet --upgrade pip
	$(PYTHON) -m pip install --quiet -r requirements.lock
	$(PYTHON) -m pip install --quiet --no-deps -e .

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

format:
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

test:
	$(PYTHON) -m pytest -q

# Jolpica allows about 500 requests an hour, so a full backfill takes roughly 2.5 hours.
ingest:
	$(PYTHON) -m ingestion.run --source all --seasons $(SEASONS)

ingest-jolpica:
	$(PYTHON) -m ingestion.run --source jolpica --seasons $(SEASONS)

# Exits 75 while a live F1 session locks the API; rerun after the session ends.
ingest-openf1:
	$(PYTHON) -m ingestion.run --source openf1 --seasons $(SEASONS)

all: lint test
