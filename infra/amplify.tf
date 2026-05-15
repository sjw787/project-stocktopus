locals {
  amplify_enabled = var.github_access_token != "" && var.github_repository != ""
}

resource "aws_amplify_app" "frontend" {
  count      = local.amplify_enabled ? 1 : 0
  name       = local.name_prefix
  repository = var.github_repository

  access_token = var.github_access_token

  platform = "WEB" # static Vite SPA — not SSR

  build_spec = <<-YAML
    version: 1
    applications:
      - appRoot: frontend
        frontend:
          phases:
            preBuild:
              commands:
                - npm ci
            build:
              commands:
                - npm run build
          artifacts:
            baseDirectory: dist
            files:
              - "**/*"
          cache:
            paths:
              - node_modules/**/*
  YAML

  # SPA deep-link routing — rewrite all non-asset paths to index.html
  custom_rule {
    source = "</^[^.]+$|\\.(?!(css|gif|ico|jpg|js|png|txt|svg|woff|woff2|ttf|eot|map|json)$)([^.]+$)/>"
    status = "200"
    target = "/index.html"
  }

  environment_variables = {
    VITE_API_URL           = var.custom_domain_enabled ? "https://${var.api_subdomain}" : (local.lambda_enabled ? aws_api_gateway_stage.prod[0].invoke_url : "")
    VITE_COGNITO_REGION    = var.aws_region
    VITE_COGNITO_USER_POOL = aws_cognito_user_pool.main.id
    VITE_COGNITO_CLIENT_ID = aws_cognito_user_pool_client.web.id
    VITE_COGNITO_DOMAIN    = "${aws_cognito_user_pool_domain.main.domain}.auth.${var.aws_region}.amazoncognito.com"
  }

  tags = { Name = local.name_prefix }
}

resource "aws_amplify_branch" "main" {
  count       = local.amplify_enabled ? 1 : 0
  app_id      = aws_amplify_app.frontend[0].id
  branch_name = var.github_branch

  enable_auto_build           = true
  enable_pull_request_preview = false

  framework = "Vite"
  stage     = var.environment == "prod" ? "PRODUCTION" : "DEVELOPMENT"

  environment_variables = {
    VITE_API_URL = var.custom_domain_enabled ? "https://${var.api_subdomain}" : (local.lambda_enabled ? aws_api_gateway_stage.prod[0].invoke_url : "")
  }
}

resource "aws_amplify_domain_association" "main" {
  count  = local.amplify_enabled && var.custom_domain_enabled ? 1 : 0
  app_id = aws_amplify_app.frontend[0].id

  domain_name = var.domain_name

  sub_domain {
    branch_name = aws_amplify_branch.main[0].branch_name
    prefix      = ""
  }
}

# Amplify generates its own ACM cert for the CloudFront distribution.
# It writes the validation CNAME into whatever zone it finds/creates.
# Since our authoritative zone is managed by Terraform, we mirror those
# records here so DNS validation resolves correctly.
resource "aws_route53_record" "amplify_cert_validation" {
  count   = local.amplify_enabled && var.custom_domain_enabled ? 1 : 0
  zone_id = local.zone_id
  name    = "_d26578c915545ca085215f073c083e11.${var.domain_name}"
  type    = "CNAME"
  ttl     = 60
  records = ["_489044c1d0b3458a137b104f085bfbfa.jkddzztszm.acm-validations.aws."]
}

# Root apex alias: stocktopus.samwylock.com → Amplify CloudFront
resource "aws_route53_record" "amplify_root" {
  count   = local.amplify_enabled && var.custom_domain_enabled ? 1 : 0
  zone_id = local.zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = "d213o9xg5f5taz.cloudfront.net"
    zone_id                = "Z2FDTNDATAQYW2"
    evaluate_target_health = false
  }
}

output "amplify_default_url" {
  description = "Amplify app default domain"
  sensitive   = true
  value       = local.amplify_enabled ? "https://${aws_amplify_branch.main[0].branch_name}.${aws_amplify_app.frontend[0].default_domain}" : "Amplify not configured — set github_access_token"
}

output "amplify_app_id" {
  description = "Amplify App ID"
  sensitive   = true
  value       = local.amplify_enabled ? aws_amplify_app.frontend[0].id : "N/A"
}
