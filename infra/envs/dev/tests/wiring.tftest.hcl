mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
    }
  }
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
  mock_resource "aws_s3_bucket" {
    defaults = {
      arn = "arn:aws:s3:::f1-race-analytics-123456789012"
    }
  }
  mock_resource "aws_lambda_function" {
    defaults = {
      arn = "arn:aws:lambda:eu-west-1:123456789012:function:f1"
    }
  }
  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::123456789012:role/f1"
    }
  }
  mock_resource "aws_sns_topic" {
    defaults = {
      arn = "arn:aws:sns:eu-west-1:123456789012:f1-alerts"
    }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = {
      arn = "arn:aws:logs:eu-west-1:123456789012:log-group:f1"
    }
  }
  mock_resource "aws_sfn_state_machine" {
    defaults = {
      arn = "arn:aws:states:eu-west-1:123456789012:stateMachine:f1-race-analytics"
    }
  }
}

variables {
  alert_email = "alerts@example.com"
}

run "first_apply_creates_no_pipeline" {
  command = plan

  assert {
    condition     = length(aws_lambda_function.fn) == 0 && length(aws_sfn_state_machine.pipeline) == 0
    error_message = "Without an image tag there is nothing to run, so no Lambda or state machine."
  }

  assert {
    condition     = output.lake_bucket == "f1-race-analytics-123456789012"
    error_message = "The bucket name must include the account ID, because names are global."
  }

  assert {
    condition     = aws_athena_workgroup.f1.configuration[0].bytes_scanned_cutoff_per_query <= 1073741824
    error_message = "Athena queries must stop at 1 GB scanned."
  }

  assert {
    condition     = aws_athena_workgroup.f1.configuration[0].enforce_workgroup_configuration
    error_message = "Clients must not be able to override the workgroup's limits."
  }

  assert {
    condition     = aws_ecr_repository.pipeline.image_tag_mutability == "IMMUTABLE" && aws_ecr_repository.pipeline.image_scanning_configuration[0].scan_on_push
    error_message = "Images must be immutable and scanned on push."
  }

  assert {
    condition     = length(aws_glue_catalog_table.silver) == 8
    error_message = "Every silver table needs a Glue table."
  }

  assert {
    condition     = alltrue([for t in aws_glue_catalog_table.silver : t.parameters["projection.enabled"] == "true"])
    error_message = "Silver tables use partition projection, so no partition needs registering."
  }

  assert {
    condition     = alltrue([for g in aws_cloudwatch_log_group.fn : g.retention_in_days == 14])
    error_message = "Logs must expire so they do not accumulate cost."
  }
}

run "pipeline_is_wired_once_an_image_exists" {
  # Apply against the mock provider: the definition embeds ARNs only known after apply.
  command = apply

  variables {
    image_tag = "abc1234"
  }

  assert {
    condition     = length(aws_lambda_function.fn) == 3
    error_message = "Ingest, silver and dbt each need a function."
  }

  assert {
    condition     = aws_lambda_function.fn["ingest"].image_config[0].command[0] == "ingestion.lambda_handler.ingest_handler"
    error_message = "Each function must run its own handler."
  }

  assert {
    condition     = strcontains(aws_sfn_state_machine.pipeline[0].definition, "LiveSessionLockError")
    error_message = "The state machine must retry OpenF1's live-session lock rather than fail."
  }

  assert {
    condition     = jsondecode(aws_sfn_state_machine.pipeline[0].definition).States.MoreToFetch.Choices[0].Next == "Ingest"
    error_message = "Ingest must loop until complete, because one Lambda run is capped at 15 minutes."
  }

  assert {
    condition     = aws_scheduler_schedule.pipeline[0].schedule_expression == "cron(0 6 ? * MON,THU *)"
    error_message = "The pipeline runs Monday and Thursday mornings."
  }
}
