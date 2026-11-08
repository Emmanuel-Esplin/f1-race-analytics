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

| Layer | Local | AWS (planned) |
| --- | --- | --- |
| Ingestion | Python, httpx, tenacity | Lambda container on an EventBridge schedule |
| Storage | `data/bronze`, `data/silver` | S3 |
| Transform | dbt on DuckDB | dbt on Athena, Iceberg tables |
| Orchestration | Makefile | Step Functions |
| Infrastructure | n/a | Terraform |

## Run it

```bash
make install
make test
make ingest          # full backfill takes about 2.5 hours (Jolpica allows ~500 requests/hour)
```

## Status

- [x] Phase 1: ingestion to bronze
- [ ] Phase 2: silver and dbt marts on DuckDB
- [ ] Phase 3: reconciliation against known results
- [ ] Phase 4: dashboard
- [ ] Phase 5: AWS

## Data

Race data comes from the [Jolpica F1 API](https://github.com/jolpica/jolpica-f1) and
[OpenF1](https://openf1.org). Neither is affiliated with Formula 1. Raw data is not committed.

## License

MIT
