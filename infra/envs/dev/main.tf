data "aws_caller_identity" "current" {}

locals {
  name   = "f1-race-analytics"
  bucket = "${local.name}-${data.aws_caller_identity.current.account_id}"
  # Generated from processing/silver.py by `make schemas`, so Glue always matches the Parquet.
  silver_schemas = jsondecode(file("${path.module}/../../silver_schemas.json"))
}

# --- Storage and catalog --------------------------------------------------------------------

module "lake" {
  source        = "../../modules/s3_lake"
  bucket_name   = local.bucket
  force_destroy = true
}

module "budget" {
  source            = "../../modules/budget"
  name              = "${local.name}-monthly"
  monthly_limit_usd = var.monthly_budget_usd
  alert_email       = var.alert_email
}

resource "aws_glue_catalog_database" "silver" {
  name = "f1_race_analytics_silver"
}

# dbt creates its tables here; Terraform only owns the database.
resource "aws_glue_catalog_database" "marts" {
  name = "f1_race_analytics_marts"
}

resource "aws_glue_catalog_table" "silver" {
  for_each      = local.silver_schemas
  name          = each.key
  database_name = aws_glue_catalog_database.silver.name
  table_type    = "EXTERNAL_TABLE"

  # Partition projection: Athena works out season=YYYY folders itself, so no crawler and no
  # partition registration after each run.
  parameters = {
    classification              = "parquet"
    "projection.enabled"        = "true"
    "projection.season.type"    = "integer"
    "projection.season.range"   = "2023,2040"
    "storage.location.template" = "s3://${local.bucket}/silver/${each.key}/season=$${season}/"
  }

  partition_keys {
    name = "season"
    type = "bigint"
  }

  storage_descriptor {
    location      = "s3://${local.bucket}/silver/${each.key}/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    dynamic "columns" {
      for_each = each.value
      content {
        name = columns.value.name
        type = columns.value.type
      }
    }
  }
}

resource "aws_athena_workgroup" "f1" {
  name          = local.name
  force_destroy = true

  configuration {
    # Clients can't raise the scan cap or send results elsewhere.
    enforce_workgroup_configuration    = true
    bytes_scanned_cutoff_per_query     = 1073741824
    publish_cloudwatch_metrics_enabled = false

    result_configuration {
      output_location = "s3://${local.bucket}/athena-results/"
      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}

# --- Container image ------------------------------------------------------------------------

resource "aws_ecr_repository" "pipeline" {
  name = local.name
  # Immutable tags: a pushed tag always means the same image, so a deploy is reproducible.
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "pipeline" {
  repository = aws_ecr_repository.pipeline.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last three images; older ones only cost storage."
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 3
      }
      action = { type = "expire" }
    }]
  })
}
