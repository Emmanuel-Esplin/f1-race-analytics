mock_provider "aws" {}

variables {
  name              = "test"
  monthly_limit_usd = 10
  alert_email       = "alerts@example.com"
}

run "credits_do_not_hide_spend" {
  command = plan

  assert {
    condition     = aws_budgets_budget.monthly.cost_types[0].include_credit == false
    error_message = "Budget must exclude credits, or alerts stay silent while credits drain."
  }

  assert {
    condition     = aws_budgets_budget.monthly.cost_types[0].include_refund == false
    error_message = "Budget must exclude refunds."
  }

  assert {
    condition     = length(aws_budgets_budget.monthly.notification) == 2
    error_message = "Budget needs both actual and forecast alerts."
  }
}
