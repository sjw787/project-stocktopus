data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.name_prefix}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

# Basic Lambda execution (CloudWatch Logs + VPC ENI management)
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# DynamoDB — settings + feature-flag table
resource "aws_iam_role_policy" "lambda_dynamodb" {
  name = "lambda-dynamodb"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan",
        ]
        Resource = aws_dynamodb_table.settings.arn
      }
    ]
  })
}

# Secrets Manager — app secrets + Aurora master password
resource "aws_iam_role_policy" "lambda_secrets" {
  name = "lambda-secrets"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = [
          aws_secretsmanager_secret.openai.arn,
          aws_secretsmanager_secret.anthropic.arn,
          aws_secretsmanager_secret.alpaca.arn,
          aws_secretsmanager_secret.finnhub.arn,
          aws_secretsmanager_secret.newsapi.arn,
          local.db_secret_arn,
        ]
      }
    ]
  })
}

# ── EventBridge Scheduler role ────────────────────────────────────────────────

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
  name               = "${local.name_prefix}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

resource "aws_iam_role_policy" "scheduler_invoke" {
  name = "invoke-lambda"
  role = aws_iam_role.scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = local.lambda_enabled ? aws_lambda_function.app[0].arn : "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${local.name_prefix}"
      }
    ]
  })
}

# ── GitHub Actions OIDC role ──────────────────────────────────────────────────

data "aws_iam_openid_connect_provider" "github" {
  count = var.github_repo_slug != "" ? 1 : 0
  url   = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github" {
  count           = var.github_repo_slug != "" && length(data.aws_iam_openid_connect_provider.github) == 0 ? 1 : 0
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

locals {
  github_oidc_provider_arn = (
    var.github_repo_slug != "" ?
    (length(data.aws_iam_openid_connect_provider.github) > 0 ?
      data.aws_iam_openid_connect_provider.github[0].arn :
      aws_iam_openid_connect_provider.github[0].arn
    ) : ""
  )
}

data "aws_iam_policy_document" "github_actions_assume" {
  count = var.github_repo_slug != "" ? 1 : 0

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo_slug}:*"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  count              = var.github_repo_slug != "" ? 1 : 0
  name               = "${local.name_prefix}-github-actions"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume[0].json
}

resource "aws_iam_role_policy" "github_actions_deploy" {
  count = var.github_repo_slug != "" ? 1 : 0
  name  = "deploy-permissions"
  role  = aws_iam_role.github_actions[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ECR"
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage",
          "ecr:DescribeImages",
          "ecr:ListImages",
        ]
        Resource = "*"
      },
      {
        Sid    = "LambdaUpdate"
        Effect = "Allow"
        Action = [
          "lambda:UpdateFunctionCode",
          "lambda:GetFunction",
          "lambda:InvokeFunction",
        ]
        Resource = local.lambda_enabled ? [
          aws_lambda_function.app[0].arn,
          aws_lambda_function.migrate[0].arn,
        ] : ["arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${local.name_prefix}*"]
      },
      {
        Sid    = "TerraformState"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
        ]
        Resource = [
          "arn:aws:s3:::stocktopus-tf-state-${data.aws_caller_identity.current.account_id}",
          "arn:aws:s3:::stocktopus-tf-state-${data.aws_caller_identity.current.account_id}/*",
        ]
      },
      {
        Sid    = "TerraformLock"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:DeleteItem",
        ]
        Resource = "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/stocktopus-tf-lock"
      },
      {
        Sid    = "TerraformIAC"
        Effect = "Allow"
        Action = [
          "iam:*",
          "lambda:*",
          "apigateway:*",
          "ecr:*",
          "logs:*",
          "dynamodb:*",
          "secretsmanager:*",
          "cognito-idp:*",
          "amplify:*",
          "rds:*",
          "ec2:*",
          "scheduler:*",
          "route53:*",
          "acm:*",
        ]
        Resource = "*"
      }
    ]
  })
}

output "github_actions_role_arn" {
  description = "IAM role ARN for GitHub Actions OIDC deploy"
  value       = var.github_repo_slug != "" ? aws_iam_role.github_actions[0].arn : "N/A — set github_repo_slug variable"
}
