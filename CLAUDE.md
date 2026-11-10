# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

F1 analytics lakehouse (2023 onward) answering five questions: race/sprint winners, crashes per
race, race time lost to crashes, lap-by-lap leaders plus championship progression, and penalties
per driver. Metric definitions and data caveats are in `docs/metrics.md`; read it before changing
any parsing rule or mart.

## Commands

All targets run through the Makefile, which uses `.venv/bin/python` and sets `PYTHONPATH`.

```bash
make install        # venv in .venv.nosync (symlinked to .venv), data.nosync symlinked to data
make lint           # ruff check + ruff format --check (line length 100)
make format         # ruff fix + format
make test           # pytest -q
make all            # lint + test
make silver         # rebuild every silver table from all of bronze (seconds)
make gold           # silver, then `dbt build` on DuckDB -> data/gold/warehouse.duckdb
make dashboard      # Streamlit on 127.0.0.1:8501 (reads the DuckDB warehouse)
make schemas        # regenerate infra/silver_schemas.json from processing/silver.py
make tf-check       # terraform fmt/validate/test; needs no AWS credentials (mocked provider)
```

Single test: `.venv/bin/python -m pytest tests/test_silver.py::test_lap_time_ms -q`

Single dbt model (from `transform/`, with `F1_DATA_DIR` pointing at the data root):
`F1_DATA_DIR="$PWD/../data" ../.venv/bin/dbt build --profiles-dir . --select mart_race_winners`

`make ingest` hits the live APIs and takes ~2.5 hours for a full backfill (Jolpica allows
~500 requests/hour). OpenF1 ingestion exits with code 75 while a live F1 session locks the API.
Don't run ingestion or any AWS target (`tf-plan`, `tf-apply`, `image-push`, `bronze-upload`,
`pipeline-run`, `dbt-athena`) unless asked.

CI (`.github/workflows/ci.yml`) also runs `dbt parse`, gitleaks, pip-audit, zizmor and checkov.

## Environment quirks

- The repo path contains a space ("Data Engineer"); quote paths in shell commands.
- The repo lives in an iCloud-synced Desktop. Anything large or hot (venv, data, Terraform
  providers, plan files) goes in a `*.nosync` path so iCloud doesn't offload it and hang reads.
  `TF_DATA_DIR` is `.terraform.nosync`.
- `PYTHONPATH` is set explicitly because macOS can hide the editable-install `.pth` file.

## Architecture

```
Jolpica + OpenF1 APIs -> bronze (raw JSON) -> silver (Parquet) -> dbt -> marts -> Streamlit
```

The same Python code runs locally and in AWS Lambda; only `F1_DATA_DIR` changes.

- **Storage abstraction** (`ingestion/landing.py`): `Storage` wraps pyarrow filesystems, so
  `F1_DATA_DIR` can be `data` or `s3://<bucket>`. Bronze files are Hive-style paths
  (`bronze/<source>/<endpoint>/season=2023/round=01.json`) wrapped in an envelope with
  `fetched_at` and `source_url`. `store()` is cached; tests clear it via the autouse fixture in
  `tests/conftest.py`, which points `F1_DATA_DIR` at a tmp dir.
- **Ingestion** (`ingestion/`): `client.ApiClient` does rate limiting, tenacity retries,
  a `deadline` (raises `OutOfTimeError` so Lambda can stop early and resume), and
  `LiveSessionLockError` for OpenF1. Ingestion is idempotent: a file is skipped once
  `is_final` (fetched after `SETTLE_DAYS` = 3 days post-race, since stewards can change results).
- **Silver** (`processing/silver.py`): `SCHEMAS` (pyarrow schemas) and `TABLES` (endpoint ->
  row builder) are the single source of truth for silver columns. Silver is always rebuilt in
  full, one Parquet file per season. Glue table definitions are generated from `SCHEMAS` into
  `infra/silver_schemas.json` (`make schemas`), and `test_terraform_schemas_match_silver`
  fails if they drift — so after changing a silver schema, run `make schemas`.
- **dbt** (`transform/`): staging (views) -> intermediate (tables) -> marts (tables). Every
  model must run on both DuckDB (local target) and Athena/Trino Iceberg (`athena` target), so
  SQL avoids engine-specific features (no `QUALIFY`, `arg_max`, `any_value`). Engine
  differences go through macros in `transform/macros/silver.sql` (`silver()` reads Parquet
  locally or the Glue source on Athena; `iso_timestamp`, `seconds_between`). Custom generic tests
  are in `macros/tests.sql`; singular tests in `transform/tests/`.
  `assert_known_2023_australia` (tag `reconcile`) only passes on real data.
- **Tests**: no test calls a live API (httpx `MockTransport`). `tests/test_dbt_pipeline.py`
  builds an invented race end to end (bronze -> silver -> full `dbt build` on DuckDB), so the
  repo holds no third-party data.
- **Dashboard** (`dashboard/app.py`): Streamlit + Altair reading the DuckDB warehouse read-only.
  Its dependencies are in `dashboard/requirements.txt`, deliberately kept out of
  `requirements.lock` so they never reach the Lambda image. Theme colours live in
  `.streamlit/config.toml`.
- **AWS** (`infra/`, `Dockerfile`, `ingestion/lambda_handler.py`): one arm64 Lambda container
  image with three handlers (`ingest_handler`, `silver_handler`, `dbt_handler`), orchestrated by
  Step Functions (ingest loops until complete, then silver, then dbt) on an EventBridge
  schedule. The Dockerfile strips DuckDB and dev tools from the lock file and runs `dbt parse`
  at build time. ECR tags are immutable and equal the git commit, so `image-push` requires a
  clean tree. Terraform modules (`budget`, `s3_lake`) and `envs/dev` each have `.tftest.hcl`
  tests; accepted checkov exceptions are documented in `.checkov.yaml`.

## Dependencies

`requirements.lock` is the pinned install set (used by `make install`, CI and the Docker image);
`pyproject.toml` lists ranges. DuckDB is pinned `<2` on purpose. Dependencies, GitHub Actions
(by commit SHA) and the Lambda base image (by digest) are all pinned — keep it that way
(see `SECURITY.md`).
