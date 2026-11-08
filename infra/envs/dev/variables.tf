variable "region" {
  type        = string
  default     = "eu-west-1"
  description = "Same region as the account's other projects."
}

variable "alert_email" {
  type        = string
  description = "Budget and pipeline-failure alerts. Set it in terraform.tfvars, which git ignores."
}

variable "monthly_budget_usd" {
  type        = number
  default     = 10
  description = "Alert level for monthly spend before credits. It alerts; it does not stop spend."
}

variable "image_tag" {
  type        = string
  default     = ""
  description = "Pipeline image tag in ECR. Empty on the first apply, before any image is pushed."
}

variable "schedule_enabled" {
  type        = bool
  default     = true
  description = "Run the pipeline every Monday and Thursday."
}
