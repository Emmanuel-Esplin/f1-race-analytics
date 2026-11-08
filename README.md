# F1 race analytics

A data engineering portfolio project on Formula 1, 2023 onward. It answers:

- who won each race and sprint
- how many crashes each race had
- how much race time was lost to crashes (Safety Car, VSC and red flag minutes)
- who led each race lap by lap, and who leads the championship after each round
- how many penalties each driver received

Definitions and data caveats are in [docs/metrics.md](docs/metrics.md).

## Architecture

```
Jolpica API ─┐                                      ┌─> marts (DuckDB locally, Athena on AWS)
             ├─> bronze (raw JSON) ─> silver (Parquet) ─> dbt ─┤
OpenF1 API  ─┘                                      └─> Streamlit dashboard
```

| Layer | Local | AWS (deployed, eu-west-1) |
| --- | --- | --- |
| Ingestion | Python, httpx, tenacity | Lambda container (arm64), EventBridge Scheduler Mon/Thu |
| Storage | `data/bronze`, `data/silver` | S3 |
| Silver | Parquet files | Parquet in S3, Glue tables with partition projection |
| Transform | dbt on DuckDB | dbt on Athena (Iceberg), run from Lambda |
| Orchestration | Makefile | Step Functions (ingest loops until done, then silver, then dbt) |
| Infrastructure | n/a | Terraform |

## Run it

```bash
make install
make test
make ingest          # full backfill takes about 2.5 hours (Jolpica allows ~500 requests/hour)
```

## Status

- [x] Phase 1: ingestion to bronze
- [x] Phase 2: silver and dbt marts for all five questions
- [x] Phase 3: reconciliation against a known race (more to add)
- [ ] Phase 4: dashboard
- [x] Phase 5: AWS (Terraform, Lambda, Step Functions, Athena)

## Security

See [SECURITY.md](SECURITY.md): locked and audited dependencies, pinned actions and base image,
IaC scanning, least-privilege IAM per pipeline step, and no long-lived keys.

## Data

Race data comes from the [Jolpica F1 API](https://github.com/jolpica/jolpica-f1) and
[OpenF1](https://openf1.org). Neither is affiliated with Formula 1. Raw data is not committed.

## License

MIT
