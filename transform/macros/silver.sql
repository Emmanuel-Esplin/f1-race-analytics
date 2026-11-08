{# A silver table: Parquet partitioned by season locally, the Glue table on Athena. #}
{% macro silver(table) %}
  {%- if target.type == 'duckdb' -%}
    read_parquet('{{ var("silver_dir") }}/{{ table }}/*/*.parquet', hive_partitioning = false)
  {%- else -%}
    {{ source('silver', table) }}
  {%- endif -%}
{% endmacro %}

{# ISO-8601 text with offset (OpenF1) to a UTC timestamp without time zone. #}
{% macro iso_timestamp(column) %}
  {%- if target.type == 'duckdb' -%}
    cast(timezone('UTC', cast({{ column }} as timestamptz)) as timestamp)
  {%- else -%}
    cast(from_iso8601_timestamp({{ column }}) at time zone 'UTC' as timestamp)
  {%- endif -%}
{% endmacro %}

{# Seconds between two timestamps, with fractions. #}
{% macro seconds_between(start, finish) %}
  {%- if target.type == 'duckdb' -%}
    (epoch({{ finish }}) - epoch({{ start }}))
  {%- else -%}
    (to_unixtime({{ finish }}) - to_unixtime({{ start }}))
  {%- endif -%}
{% endmacro %}
