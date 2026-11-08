# One image for the three pipeline Lambdas (ingest, silver, dbt); the handler is set per function.
# The base is pinned by digest so a re-tagged upstream image can't change what we ship.
FROM public.ecr.aws/lambda/python:3.12@sha256:238f6bfd2c1c188aff3955c2f7ceb767fe9da1b3597d84264426a11690fcf2d7

COPY requirements.lock ${LAMBDA_TASK_ROOT}/
# DuckDB and the dev tools are local-only; leaving them out halves the image.
RUN grep -v -i -E '^(duckdb|dbt-duckdb|pytest|ruff|iniconfig|pluggy|pygments)==' \
        ${LAMBDA_TASK_ROOT}/requirements.lock > /tmp/requirements.txt && \
    pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

COPY ingestion/ ${LAMBDA_TASK_ROOT}/ingestion/
COPY processing/ ${LAMBDA_TASK_ROOT}/processing/
COPY transform/ ${LAMBDA_TASK_ROOT}/transform/

# Parse the dbt project at build time, so a broken model fails here and not in AWS.
RUN cd ${LAMBDA_TASK_ROOT}/transform && \
    DBT_TARGET_PATH=/tmp/target DBT_LOG_PATH=/tmp/logs DBT_SEND_ANONYMOUS_USAGE_STATS=false \
    LAKE_BUCKET=build-check dbt parse --profiles-dir . --target athena && rm -rf /tmp/target /tmp/logs

CMD ["ingestion.lambda_handler.ingest_handler"]
