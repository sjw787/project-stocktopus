resource "aws_secretsmanager_secret" "openai" {
  name                    = "${local.name_prefix}/openai-api-key"
  recovery_window_in_days = 7
  tags                    = merge(local.component_tags.secrets, { Name = "${local.name_prefix}/openai" })
}

resource "aws_secretsmanager_secret_version" "openai" {
  secret_id     = aws_secretsmanager_secret.openai.id
  secret_string = var.openai_api_key != "" ? jsonencode({ api_key = var.openai_api_key }) : jsonencode({ api_key = "PLACEHOLDER" })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

resource "aws_secretsmanager_secret" "anthropic" {
  name                    = "${local.name_prefix}/anthropic-api-key"
  recovery_window_in_days = 7
  tags                    = merge(local.component_tags.secrets, { Name = "${local.name_prefix}/anthropic" })
}

resource "aws_secretsmanager_secret_version" "anthropic" {
  secret_id     = aws_secretsmanager_secret.anthropic.id
  secret_string = var.anthropic_api_key != "" ? jsonencode({ api_key = var.anthropic_api_key }) : jsonencode({ api_key = "PLACEHOLDER" })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

resource "aws_secretsmanager_secret" "alpaca" {
  name                    = "${local.name_prefix}/alpaca"
  recovery_window_in_days = 7
  tags                    = merge(local.component_tags.secrets, { Name = "${local.name_prefix}/alpaca" })
}

resource "aws_secretsmanager_secret_version" "alpaca" {
  secret_id = aws_secretsmanager_secret.alpaca.id
  secret_string = jsonencode({
    api_key    = var.alpaca_api_key != "" ? var.alpaca_api_key : "PLACEHOLDER"
    secret_key = var.alpaca_secret_key != "" ? var.alpaca_secret_key : "PLACEHOLDER"
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

resource "aws_secretsmanager_secret" "finnhub" {
  name                    = "${local.name_prefix}/finnhub-api-key"
  recovery_window_in_days = 7
  tags                    = merge(local.component_tags.secrets, { Name = "${local.name_prefix}/finnhub" })
}

resource "aws_secretsmanager_secret_version" "finnhub" {
  secret_id     = aws_secretsmanager_secret.finnhub.id
  secret_string = var.finnhub_api_key != "" ? jsonencode({ api_key = var.finnhub_api_key }) : jsonencode({ api_key = "PLACEHOLDER" })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

resource "aws_secretsmanager_secret" "newsapi" {
  name                    = "${local.name_prefix}/newsapi-api-key"
  recovery_window_in_days = 7
  tags                    = merge(local.component_tags.secrets, { Name = "${local.name_prefix}/newsapi" })
}

resource "aws_secretsmanager_secret_version" "newsapi" {
  secret_id     = aws_secretsmanager_secret.newsapi.id
  secret_string = var.newsapi_api_key != "" ? jsonencode({ api_key = var.newsapi_api_key }) : jsonencode({ api_key = "PLACEHOLDER" })

  lifecycle {
    ignore_changes = [secret_string]
  }
}
