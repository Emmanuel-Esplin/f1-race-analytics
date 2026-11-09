# Usage: make install | make lint | make test | make ingest | make silver | make gold | make all
#        make schemas | make tf-check | make tf-plan | make tf-apply | make tf-destroy
#        make image-push | make bronze-upload | make pipeline-run | make dbt-athena
#        make dashboard
PYTHON ?= .venv/bin/python
BOOTSTRAP_PYTHON ?= /opt/anaconda3/bin/python
# macOS can hide the editable-install .pth under iCloud-synced Desktop, so set this explicitly.
export PYTHONPATH := $(CURDIR)
SEASONS ?= 2023-2026

# Provider binaries go in a .nosync folder, because iCloud offloading makes them hang.
export TF_DATA_DIR := .terraform.nosync
TF_DEV = terraform -chdir=infra/envs/dev
TF_OUT = $(TF_DEV) output -raw
IMAGE_TAG ?= $(shell git rev-parse --short=12 HEAD)

.PHONY: install lint format test ingest ingest-jolpica ingest-openf1 silver gold all schemas \
	tf-check tf-plan tf-apply tf-destroy image-push bronze-upload pipeline-run dbt-athena \
	dashboard

# Quoted: the repo path contains a space ("Data Engineer").
DBT = cd transform && F1_DATA_DIR="$(CURDIR)/data" DBT_SEND_ANONYMOUS_USAGE_STATS=false \
	"$(CURDIR)/.venv/bin/dbt"

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

# Silver is rebuilt from all of bronze each time; it takes seconds.
silver:
	$(PYTHON) -m processing.silver

# Builds and tests every model on DuckDB (data/gold/warehouse.duckdb).
gold: silver
	mkdir -p data/gold
	$(DBT) build --profiles-dir .

all: lint test

# Glue table columns come from processing/silver.py.
schemas:
	$(PYTHON) -m processing.schemas_export

# No AWS credentials needed: the tests use a mocked provider.
tf-check:
	terraform fmt -check -recursive infra
	$(TF_DEV) init -input=false -backend=false >/dev/null
	$(TF_DEV) validate
	$(TF_DEV) test
	for m in budget s3_lake; do \
		terraform -chdir=infra/modules/$$m init -input=false >/dev/null && \
		terraform -chdir=infra/modules/$$m test || exit 1; \
	done

# Review the plan; `make tf-apply` then applies exactly that plan. Use IMAGE_TAG= (empty) for
# the first apply, before any image exists.
tf-plan: test
	$(TF_DEV) init -input=false >/dev/null
	$(TF_DEV) plan -var image_tag=$(IMAGE_TAG) -out=tfplan.nosync

tf-apply:
	$(TF_DEV) apply tfplan.nosync

tf-destroy:
	$(TF_DEV) destroy -var image_tag=

# ECR tags are immutable, so the git commit names the image. Commit before pushing.
image-push: test
	@git diff --quiet HEAD || (echo "commit first: the image tag is the commit" && exit 1)
	aws ecr get-login-password | docker login --username AWS --password-stdin \
		$$($(TF_OUT) ecr_repository_url | cut -d/ -f1)
	docker build --platform linux/arm64 --provenance=false \
		-t $$($(TF_OUT) ecr_repository_url):$(IMAGE_TAG) .
	docker push $$($(TF_OUT) ecr_repository_url):$(IMAGE_TAG)

# Seeds S3 with the local backfill, so Lambda only ever fetches new rounds.
bronze-upload:
	aws s3 sync data/bronze s3://$$($(TF_OUT) lake_bucket)/bronze \
		--exclude "*.tmp" --only-show-errors

pipeline-run:
	aws stepfunctions start-execution --state-machine-arn $$($(TF_OUT) state_machine_arn)

# Builds the marts on Athena from this machine, with your `aws login` session.
dbt-athena:
	cd transform && LAKE_BUCKET=$$(cd .. && $(TF_OUT) lake_bucket) \
		DBT_SEND_ANONYMOUS_USAGE_STATS=false \
		"$(CURDIR)/.venv/bin/dbt" build --profiles-dir . --target athena

# Streamlit is kept out of requirements.lock, so it never lands in the Lambda image.
dashboard:
	$(PYTHON) -m pip install --quiet -r dashboard/requirements.txt
	# Bound to this machine only; drop --server.address to share on the local network.
	F1_DATA_DIR="$(CURDIR)/data" $(PYTHON) -m streamlit run dashboard/app.py \
		--server.address 127.0.0.1 --browser.gatherUsageStats false
