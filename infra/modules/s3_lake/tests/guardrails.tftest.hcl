mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
  mock_resource "aws_s3_bucket" {
    defaults = {
      arn = "arn:aws:s3:::test-lake"
    }
  }
}

variables {
  bucket_name   = "test-lake"
  force_destroy = true
}

run "lake_is_private_and_encrypted" {
  command = apply

  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.lake.block_public_acls,
      aws_s3_bucket_public_access_block.lake.block_public_policy,
      aws_s3_bucket_public_access_block.lake.ignore_public_acls,
      aws_s3_bucket_public_access_block.lake.restrict_public_buckets,
    ])
    error_message = "All four public access blocks must be on."
  }

  assert {
    condition     = one(aws_s3_bucket_server_side_encryption_configuration.lake.rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256"
    error_message = "The lake must be encrypted."
  }

  assert {
    condition     = aws_s3_bucket_versioning.lake.versioning_configuration[0].status == "Enabled"
    error_message = "The lake must be versioned."
  }
}
