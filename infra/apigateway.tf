locals {
  cors_origins_list = var.cors_origins != "" ? split(",", var.cors_origins) : []
}

resource "aws_apigatewayv2_api" "app" {
  name          = local.name_prefix
  protocol_type = "HTTP"

  dynamic "cors_configuration" {
    for_each = length(local.cors_origins_list) > 0 ? [1] : []
    content {
      allow_origins = local.cors_origins_list
      allow_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
      allow_headers = ["Authorization", "Content-Type"]
      max_age       = 86400
    }
  }
}

resource "aws_apigatewayv2_authorizer" "cognito_jwt" {
  api_id           = aws_apigatewayv2_api.app.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "cognito-jwt"

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.web.id]
    issuer   = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.main.id}"
  }
}

resource "aws_apigatewayv2_integration" "lambda" {
  count                  = local.lambda_enabled ? 1 : 0
  api_id                 = aws_apigatewayv2_api.app.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.app[0].invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = var.lambda_timeout_seconds * 1000
}

# Catch-all authenticated route — all /api/* and other paths require JWT
resource "aws_apigatewayv2_route" "proxy" {
  count              = local.lambda_enabled ? 1 : 0
  api_id             = aws_apigatewayv2_api.app.id
  route_key          = "ANY /{proxy+}"
  target             = "integrations/${aws_apigatewayv2_integration.lambda[0].id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_jwt.id
}

# Health check — no auth required
resource "aws_apigatewayv2_route" "health" {
  count     = local.lambda_enabled ? 1 : 0
  api_id    = aws_apigatewayv2_api.app.id
  route_key = "GET /health"
  target    = "integrations/${aws_apigatewayv2_integration.lambda[0].id}"
}

# OPTIONS preflight — no auth so browsers can complete CORS preflight
resource "aws_apigatewayv2_route" "options" {
  count              = local.lambda_enabled ? 1 : 0
  api_id             = aws_apigatewayv2_api.app.id
  route_key          = "OPTIONS /{proxy+}"
  target             = "integrations/${aws_apigatewayv2_integration.lambda[0].id}"
  authorization_type = "NONE"
}

resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/apigateway/${local.name_prefix}"
  retention_in_days = 30
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.app.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      responseLength = "$context.responseLength"
      errorMessage   = "$context.error.message"
    })
  }
}

# Custom domain — only activated after DNS delegation (custom_domain_enabled = true)
resource "aws_apigatewayv2_domain_name" "api" {
  count       = var.custom_domain_enabled ? 1 : 0
  domain_name = var.api_subdomain

  domain_name_configuration {
    certificate_arn = aws_acm_certificate_validation.api[0].certificate_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }
}

resource "aws_apigatewayv2_api_mapping" "api" {
  count       = var.custom_domain_enabled ? 1 : 0
  api_id      = aws_apigatewayv2_api.app.id
  domain_name = aws_apigatewayv2_domain_name.api[0].id
  stage       = aws_apigatewayv2_stage.default.id
}
