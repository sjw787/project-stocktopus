# ── REST API (v1) ─────────────────────────────────────────────────────────────
# Using REST API instead of HTTP API so we can set integration timeout > 29s.
# HTTP API v2 has a hard 29s integration limit; REST API v1 allows up to 300s
# after an AWS Service Quotas increase (Service Quotas → API Gateway →
# "Maximum integration timeout in milliseconds").

resource "aws_api_gateway_rest_api" "app" {
  name = local.name_prefix

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  # Allow all binary content types so Lambda can handle file responses
  binary_media_types = ["*/*"]

  tags = merge(local.component_tags.api, { Name = local.name_prefix })
}

# ── Cognito authorizer ────────────────────────────────────────────────────────

resource "aws_api_gateway_authorizer" "cognito" {
  name          = "cognito"
  rest_api_id   = aws_api_gateway_rest_api.app.id
  type          = "COGNITO_USER_POOLS"
  provider_arns = [aws_cognito_user_pool.main.arn]

  identity_source = "method.request.header.Authorization"
}

# ── Resources ─────────────────────────────────────────────────────────────────

# /health — unauthenticated
resource "aws_api_gateway_resource" "health" {
  rest_api_id = aws_api_gateway_rest_api.app.id
  parent_id   = aws_api_gateway_rest_api.app.root_resource_id
  path_part   = "health"
}

# /{proxy+} — catch-all, authenticated
resource "aws_api_gateway_resource" "proxy" {
  rest_api_id = aws_api_gateway_rest_api.app.id
  parent_id   = aws_api_gateway_rest_api.app.root_resource_id
  path_part   = "{proxy+}"
}

# ── Health method + integration ───────────────────────────────────────────────

resource "aws_api_gateway_method" "health_get" {
  rest_api_id   = aws_api_gateway_rest_api.app.id
  resource_id   = aws_api_gateway_resource.health.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "health" {
  count = local.lambda_enabled ? 1 : 0

  rest_api_id             = aws_api_gateway_rest_api.app.id
  resource_id             = aws_api_gateway_resource.health.id
  http_method             = aws_api_gateway_method.health_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.app[0].invoke_arn
  timeout_milliseconds    = var.api_integration_timeout_ms
}

# ── Proxy catch-all: ANY /{proxy+} ────────────────────────────────────────────

resource "aws_api_gateway_method" "proxy_any" {
  rest_api_id   = aws_api_gateway_rest_api.app.id
  resource_id   = aws_api_gateway_resource.proxy.id
  http_method   = "ANY"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id

  request_parameters = {
    "method.request.header.Authorization" = false
  }
}

resource "aws_api_gateway_integration" "proxy" {
  count = local.lambda_enabled ? 1 : 0

  rest_api_id             = aws_api_gateway_rest_api.app.id
  resource_id             = aws_api_gateway_resource.proxy.id
  http_method             = aws_api_gateway_method.proxy_any.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.app[0].invoke_arn
  timeout_milliseconds    = var.api_integration_timeout_ms
}

# ── OPTIONS /{proxy+} — CORS preflight (no auth) ─────────────────────────────
# FastAPI/Mangum returns the actual CORS headers; this method just lets
# browser preflight requests through without auth.

resource "aws_api_gateway_method" "proxy_options" {
  rest_api_id   = aws_api_gateway_rest_api.app.id
  resource_id   = aws_api_gateway_resource.proxy.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "proxy_options" {
  count = local.lambda_enabled ? 1 : 0

  rest_api_id             = aws_api_gateway_rest_api.app.id
  resource_id             = aws_api_gateway_resource.proxy.id
  http_method             = aws_api_gateway_method.proxy_options.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.app[0].invoke_arn
  timeout_milliseconds    = 29000
}

# ── CORS gateway responses ────────────────────────────────────────────────────
# Without these, a Cognito 401 or gateway 5xx appears to the browser as a
# CORS failure because API Gateway doesn't copy integration CORS headers onto
# gateway-generated error responses.

locals {
  cors_headers = {
    "gatewayresponse.header.Access-Control-Allow-Origin"  = "'*'"
    "gatewayresponse.header.Access-Control-Allow-Headers" = "'Authorization,Content-Type'"
    "gatewayresponse.header.Access-Control-Allow-Methods" = "'*'"
  }
}

resource "aws_api_gateway_gateway_response" "cors_4xx" {
  rest_api_id   = aws_api_gateway_rest_api.app.id
  response_type = "DEFAULT_4XX"

  response_parameters = local.cors_headers
}

resource "aws_api_gateway_gateway_response" "cors_5xx" {
  rest_api_id   = aws_api_gateway_rest_api.app.id
  response_type = "DEFAULT_5XX"

  response_parameters = local.cors_headers
}

# ── CloudWatch logging account-level setting ──────────────────────────────────

resource "aws_iam_role" "apigw_cloudwatch" {
  name = "${local.name_prefix}-apigw-cw"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "apigateway.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "apigw_cloudwatch" {
  role       = aws_iam_role.apigw_cloudwatch.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs"
}

resource "aws_api_gateway_account" "main" {
  cloudwatch_role_arn = aws_iam_role.apigw_cloudwatch.arn
}

resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/apigateway/${local.name_prefix}"
  retention_in_days = 30
  tags              = local.component_tags.observability
}

# ── Deployment + stage ────────────────────────────────────────────────────────
# The `triggers` map forces a new deployment whenever the API definition changes.

resource "aws_api_gateway_deployment" "app" {
  count = local.lambda_enabled ? 1 : 0

  rest_api_id = aws_api_gateway_rest_api.app.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.health.id,
      aws_api_gateway_resource.proxy.id,
      aws_api_gateway_method.health_get.id,
      aws_api_gateway_method.proxy_any.id,
      aws_api_gateway_method.proxy_options.id,
      aws_api_gateway_integration.health[0].id,
      aws_api_gateway_integration.proxy[0].id,
      aws_api_gateway_integration.proxy_options[0].id,
      aws_api_gateway_gateway_response.cors_4xx.id,
      aws_api_gateway_gateway_response.cors_5xx.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_integration.health,
    aws_api_gateway_integration.proxy,
    aws_api_gateway_integration.proxy_options,
  ]
}

resource "aws_api_gateway_stage" "prod" {
  count = local.lambda_enabled ? 1 : 0

  rest_api_id   = aws_api_gateway_rest_api.app.id
  deployment_id = aws_api_gateway_deployment.app[0].id
  stage_name    = "prod"

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      resourcePath   = "$context.resourcePath"
      status         = "$context.status"
      responseLength = "$context.responseLength"
      integrationLatency = "$context.integrationLatency"
      errorMessage   = "$context.error.message"
    })
  }

  depends_on = [aws_api_gateway_account.main]

  tags = merge(local.component_tags.api, { Name = "${local.name_prefix}-prod" })
}

resource "aws_api_gateway_method_settings" "all" {
  count = local.lambda_enabled ? 1 : 0

  rest_api_id = aws_api_gateway_rest_api.app.id
  stage_name  = aws_api_gateway_stage.prod[0].stage_name
  method_path = "*/*"

  settings {
    metrics_enabled    = true
    logging_level      = "ERROR"
    data_trace_enabled = false
  }
}

# ── Custom domain ─────────────────────────────────────────────────────────────

resource "aws_api_gateway_domain_name" "api" {
  count = var.custom_domain_enabled ? 1 : 0

  domain_name              = var.api_subdomain
  regional_certificate_arn = aws_acm_certificate_validation.api[0].certificate_arn

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = merge(local.component_tags.dns, { Name = var.api_subdomain })
}

resource "aws_api_gateway_base_path_mapping" "api" {
  count = var.custom_domain_enabled && local.lambda_enabled ? 1 : 0

  api_id      = aws_api_gateway_rest_api.app.id
  domain_name = aws_api_gateway_domain_name.api[0].domain_name
  stage_name  = aws_api_gateway_stage.prod[0].stage_name
  # empty base_path maps / on the custom domain → /prod stage
}
