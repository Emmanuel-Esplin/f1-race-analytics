# Ingest -> silver -> dbt, run by Step Functions on a schedule. Created only once an image is
# pushed (var.image_tag), because a Lambda can't be created without its image.

locals {
  deploy_pipeline = var.image_tag != ""
  bucket_arn      = module.lake.bucket_arn
  glue_arn        = "arn:aws:glue:${var.region}:${data.aws_caller_identity.current.account_id}"

  functions = {
    ingest = { handler = "ingestion.lambda_handler.ingest_handler", memory = 512 }
    silver = { handler = "ingestion.lambda_handler.silver_handler", memory = 2048 }
    dbt    = { handler = "ingestion.lambda_handler.dbt_handler", memory = 1024 }
  }
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_cloudwatch_log_group" "fn" {
  for_each          = local.functions
  name              = "/aws/lambda/${local.name}-${each.key}"
  retention_in_days = 14
}

resource "aws_iam_role" "fn" {
  for_each           = local.functions
  name               = "${local.name}-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# Each function may read and write only the prefixes its step owns.
data "aws_iam_policy_document" "fn" {
  for_each = {
    ingest = { list = ["bronze/"], read = ["bronze/"], write = ["bronze/"] }
    silver = { list = ["bronze/", "silver/"], read = ["bronze/", "silver/"], write = ["silver/"] }
    dbt = {
      list  = ["silver/", "marts/", "athena-results/"]
      read  = ["silver/", "marts/", "athena-results/"]
      write = ["marts/", "athena-results/"]
    }
  }

  statement {
    sid       = "OwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.fn[each.key].arn}:*"]
  }

  statement {
    sid       = "ListOwnPrefixes"
    actions   = ["s3:ListBucket"]
    resources = [local.bucket_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = flatten([for p in each.value.list : [p, "${p}*"]])
    }
  }

  statement {
    sid       = "ReadPrefixes"
    actions   = ["s3:GetObject"]
    resources = [for p in each.value.read : "${local.bucket_arn}/${p}*"]
  }

  statement {
    sid       = "WritePrefixes"
    actions   = ["s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload"]
    resources = [for p in each.value.write : "${local.bucket_arn}/${p}*"]
  }

  dynamic "statement" {
    for_each = each.key == "dbt" ? [1] : []
    content {
      sid = "QueryInOwnWorkgroup"
      actions = [
        "athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults",
        "athena:StopQueryExecution", "athena:GetWorkGroup",
      ]
      resources = [aws_athena_workgroup.f1.arn]
    }
  }

  dynamic "statement" {
    for_each = each.key == "dbt" ? [1] : []
    content {
      sid = "CatalogForOwnDatabases"
      actions = [
        "glue:GetDatabase", "glue:GetDatabases", "glue:GetTable", "glue:GetTables",
        "glue:GetPartition", "glue:GetPartitions", "glue:BatchGetPartition",
        "glue:CreateTable", "glue:UpdateTable", "glue:DeleteTable", "glue:BatchDeleteTable",
      ]
      resources = [
        "${local.glue_arn}:catalog",
        aws_glue_catalog_database.silver.arn,
        aws_glue_catalog_database.marts.arn,
        "${local.glue_arn}:table/${aws_glue_catalog_database.silver.name}/*",
        "${local.glue_arn}:table/${aws_glue_catalog_database.marts.name}/*",
      ]
    }
  }

  dynamic "statement" {
    for_each = each.key == "dbt" ? [1] : []
    content {
      sid       = "BucketLocationForAthena"
      actions   = ["s3:GetBucketLocation"]
      resources = [local.bucket_arn]
    }
  }
}

resource "aws_iam_role_policy" "fn" {
  for_each = local.functions
  name     = "${local.name}-${each.key}"
  role     = aws_iam_role.fn[each.key].id
  policy   = data.aws_iam_policy_document.fn[each.key].json
}

resource "aws_lambda_function" "fn" {
  for_each      = local.deploy_pipeline ? local.functions : {}
  function_name = "${local.name}-${each.key}"
  role          = aws_iam_role.fn[each.key].arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.pipeline.repository_url}:${var.image_tag}"
  architectures = ["arm64"]
  memory_size   = each.value.memory
  # Jolpica's rate limit makes ingest slow, so every step gets Lambda's maximum.
  timeout = 900

  image_config {
    command = [each.value.handler]
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.fn[each.key].name
  }

  environment {
    variables = {
      # The region in the URI saves a bucket-region lookup, which needs extra permissions.
      F1_DATA_DIR = "s3://${local.bucket}?region=${var.region}"
      LAKE_BUCKET = local.bucket
    }
  }

  depends_on = [aws_iam_role_policy.fn]
}

# --- Orchestration --------------------------------------------------------------------------

data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sfn" {
  count              = local.deploy_pipeline ? 1 : 0
  name               = "${local.name}-pipeline"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
}

resource "aws_iam_role_policy" "sfn" {
  count = local.deploy_pipeline ? 1 : 0
  name  = "${local.name}-invoke-steps"
  role  = aws_iam_role.sfn[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "lambda:InvokeFunction"
        Resource = [for fn in aws_lambda_function.fn : fn.arn]
      },
      {
        # Step Functions log delivery only works with these, and they take no resource ARN.
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery", "logs:GetLogDelivery", "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery", "logs:ListLogDeliveries", "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies", "logs:DescribeLogGroups",
        ]
        Resource = "*"
      },
    ]
  })
}

locals {
  lambda_retry = {
    ErrorEquals     = ["Lambda.ServiceException", "Lambda.TooManyRequestsException", "Lambda.SdkClientException"]
    IntervalSeconds = 10
    MaxAttempts     = 3
    BackoffRate     = 2
  }
}

resource "aws_cloudwatch_log_group" "sfn" {
  name              = "/aws/vendedlogs/states/${local.name}"
  retention_in_days = 14
}

resource "aws_sfn_state_machine" "pipeline" {
  count    = local.deploy_pipeline ? 1 : 0
  name     = local.name
  role_arn = aws_iam_role.sfn[0].arn

  # Failed steps only: enough to debug a run without paying to log every success.
  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn.arn}:*"
    include_execution_data = true
    level                  = "ERROR"
  }

  definition = jsonencode({
    Comment = "Ingest new F1 data, rebuild silver, then build and test the marts."
    StartAt = "Ingest"
    States = {
      Ingest = {
        Type       = "Task"
        Resource   = "arn:aws:states:::lambda:invoke"
        Parameters = { FunctionName = aws_lambda_function.fn["ingest"].arn, "Payload.$" = "$" }
        OutputPath = "$.Payload"
        Retry = [
          # OpenF1 locks out anonymous clients during a live session; wait it out.
          { ErrorEquals = ["LiveSessionLockError"], IntervalSeconds = 3600, MaxAttempts = 6, BackoffRate = 1 },
          local.lambda_retry,
        ]
        Next = "MoreToFetch"
      }
      # Ingest stops before Lambda's 15-minute limit; loop until it has fetched everything.
      MoreToFetch = {
        Type    = "Choice"
        Choices = [{ Variable = "$.complete", BooleanEquals = false, Next = "Ingest" }]
        Default = "Silver"
      }
      Silver = {
        Type       = "Task"
        Resource   = "arn:aws:states:::lambda:invoke"
        Parameters = { FunctionName = aws_lambda_function.fn["silver"].arn, Payload = {} }
        OutputPath = "$.Payload"
        Retry      = [local.lambda_retry]
        Next       = "Marts"
      }
      Marts = {
        Type       = "Task"
        Resource   = "arn:aws:states:::lambda:invoke"
        Parameters = { FunctionName = aws_lambda_function.fn["dbt"].arn, Payload = { command = "build" } }
        OutputPath = "$.Payload"
        Retry      = [local.lambda_retry]
        End        = true
      }
    }
  })
}

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  count              = local.deploy_pipeline ? 1 : 0
  name               = "${local.name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

resource "aws_iam_role_policy" "scheduler" {
  count = local.deploy_pipeline ? 1 : 0
  name  = "${local.name}-start-pipeline"
  role  = aws_iam_role.scheduler[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "states:StartExecution"
      Resource = aws_sfn_state_machine.pipeline[0].arn
    }]
  })
}

# Monday picks up the weekend's race; Thursday refetches it once results have settled.
resource "aws_scheduler_schedule" "pipeline" {
  count               = local.deploy_pipeline ? 1 : 0
  name                = "${local.name}-twice-weekly"
  schedule_expression = "cron(0 6 ? * MON,THU *)"
  state               = var.schedule_enabled ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.pipeline[0].arn
    role_arn = aws_iam_role.scheduler[0].arn
    input    = jsonencode({})
  }
}

# --- Alerts ---------------------------------------------------------------------------------

resource "aws_sns_topic" "alerts" {
  name = "${local.name}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

data "aws_iam_policy_document" "alerts" {
  statement {
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_cloudwatch_event_rule.pipeline_failed.arn]
    }
  }
}

resource "aws_sns_topic_policy" "alerts" {
  arn    = aws_sns_topic.alerts.arn
  policy = data.aws_iam_policy_document.alerts.json
}

resource "aws_cloudwatch_event_rule" "pipeline_failed" {
  name = "${local.name}-pipeline-failed"
  event_pattern = jsonencode({
    source        = ["aws.states"]
    "detail-type" = ["Step Functions Execution Status Change"]
    detail = {
      status          = ["FAILED", "TIMED_OUT", "ABORTED"]
      stateMachineArn = [{ prefix = "arn:aws:states:${var.region}:${data.aws_caller_identity.current.account_id}:stateMachine:${local.name}" }]
    }
  })
}

resource "aws_cloudwatch_event_target" "pipeline_failed" {
  rule = aws_cloudwatch_event_rule.pipeline_failed.name
  arn  = aws_sns_topic.alerts.arn
}
