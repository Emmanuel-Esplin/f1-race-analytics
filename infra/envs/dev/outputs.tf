output "lake_bucket" { value = module.lake.bucket_name }
output "ecr_repository_url" { value = aws_ecr_repository.pipeline.repository_url }
output "athena_workgroup" { value = aws_athena_workgroup.f1.name }
output "state_machine_arn" {
  value = one(aws_sfn_state_machine.pipeline[*].arn)
}
