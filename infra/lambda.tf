locals {
  lambda_enabled = var.image_uri != ""
}

# ── Log groups ─────────────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name_prefix}"
  retention_in_days = 90
}

resource "aws_cloudwatch_log_group" "lambda_migrate" {
  name              = "/aws/lambda/${local.name_prefix}-migrate"
  retention_in_days = 30
}

# ── App Lambda ─────────────────────────────────────────────────────────────────

resource "aws_lambda_function" "app" {
  count         = local.lambda_enabled ? 1 : 0
  function_name = local.name_prefix
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = var.image_uri
  architectures = ["arm64"]
  memory_size   = var.lambda_memory_mb
  timeout       = var.lambda_timeout_seconds

  vpc_config {
    subnet_ids         = aws_subnet.private_lambda[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = local.app_env
  }

  lifecycle {
    ignore_changes = [image_uri]
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy_attachment.lambda_basic,
    aws_iam_role_policy.lambda_dynamodb,
    aws_iam_role_policy.lambda_secrets,
  ]
}

# ── Migration Lambda (same image, different CMD) ───────────────────────────────

resource "aws_lambda_function" "migrate" {
  count         = local.lambda_enabled ? 1 : 0
  function_name = "${local.name_prefix}-migrate"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = var.image_uri
  architectures = ["arm64"]
  memory_size   = 512
  timeout       = 300

  image_config {
    command = ["stocktopus.db.migrations.lambda_migrate.handler"]
  }

  vpc_config {
    subnet_ids         = aws_subnet.private_lambda[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = local.db_env
  }

  lifecycle {
    ignore_changes = [image_uri]
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda_migrate,
  ]
}

# ── Permissions ────────────────────────────────────────────────────────────────

resource "aws_lambda_permission" "api_gateway" {
  count         = local.lambda_enabled ? 1 : 0
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.app[0].function_name
  principal     = "apigateway.amazonaws.com"
  # /*/*/*  allows all stages, methods, and nested proxy resource paths
  source_arn    = "${aws_api_gateway_rest_api.app.execution_arn}/*/*/*"
}

resource "aws_lambda_permission" "scheduler" {
  count         = local.lambda_enabled ? 1 : 0
  statement_id  = "AllowEventBridgeSchedulerInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.app[0].function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = "arn:aws:scheduler:${var.aws_region}:${data.aws_caller_identity.current.account_id}:schedule/*/*"
}
