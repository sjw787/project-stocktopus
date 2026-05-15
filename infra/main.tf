terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.50.0, < 6.0.0"
    }
  }

  backend "s3" {
    # Set via -backend-config flags or deploy/deploy.sh at init time
    # bucket = "stocktopus-tf-state-<account_id>"
    # key    = "stocktopus/<environment>/terraform.tfstate"
    # region = "us-east-1"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "stocktopus"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" { state = "available" }

locals {
  app_name    = "stocktopus"
  name_prefix = "${local.app_name}-${var.environment}"
  azs         = slice(data.aws_availability_zones.available.names, 0, 3)

  db_secret_arn = aws_rds_cluster.aurora.master_user_secret[0].secret_arn

  db_env = {
    DB_SECRET_ARN      = local.db_secret_arn
    RDS_PROXY_ENDPOINT = aws_rds_cluster.aurora.endpoint
    DB_NAME            = var.db_name
  }

  app_env = merge(local.db_env, {
    ENV                  = var.environment
    LAMBDA_RUNTIME       = "true"
    CORS_ALLOWED_ORIGINS = jsonencode(var.cors_origins != "" ? split(",", var.cors_origins) : [])
    SETTINGS_TABLE_NAME  = aws_dynamodb_table.settings.name
    OPENAI_SECRET_ARN    = aws_secretsmanager_secret.openai.arn
    ANTHROPIC_SECRET_ARN = aws_secretsmanager_secret.anthropic.arn
    ALPACA_SECRET_ARN    = aws_secretsmanager_secret.alpaca.arn
    ALPACA_DATA_FEED     = var.alpaca_data_feed
    FINNHUB_SECRET_ARN   = aws_secretsmanager_secret.finnhub.arn
    NEWSAPI_SECRET_ARN   = aws_secretsmanager_secret.newsapi.arn
  })

  tags = {
    Project     = local.app_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}
