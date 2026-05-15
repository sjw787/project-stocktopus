resource "aws_scheduler_schedule_group" "main" {
  name = local.name_prefix
  tags = merge(local.component_tags.scheduling, { Name = local.name_prefix })
}

locals {
  market_hours_cron_5min  = "cron(*/5 13-20 ? * MON-FRI *)"
  market_hours_cron_15min = "cron(*/15 13-20 ? * MON-FRI *)"
}

resource "aws_scheduler_schedule" "ingestion_tick" {
  count      = local.lambda_enabled ? 1 : 0
  name       = "${local.name_prefix}-ingestion-tick"
  group_name = aws_scheduler_schedule_group.main.name

  flexible_time_window { mode = "OFF" }

  schedule_expression          = local.market_hours_cron_5min
  schedule_expression_timezone = "America/New_York"

  target {
    arn      = aws_lambda_function.app[0].arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ source = "scheduler", task = "ingestion_tick" })
    retry_policy { maximum_retry_attempts = 0 }
  }
}

resource "aws_scheduler_schedule" "paper_tick" {
  count      = local.lambda_enabled ? 1 : 0
  name       = "${local.name_prefix}-paper-tick"
  group_name = aws_scheduler_schedule_group.main.name

  flexible_time_window { mode = "OFF" }

  schedule_expression          = local.market_hours_cron_15min
  schedule_expression_timezone = "America/New_York"

  target {
    arn      = aws_lambda_function.app[0].arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ source = "scheduler", task = "paper_tick" })
    retry_policy { maximum_retry_attempts = 0 }
  }
}
