output "api_gateway_invoke_url" {
  description = "API Gateway default invoke URL (no custom domain) — includes /prod stage prefix"
  value       = local.lambda_enabled ? aws_api_gateway_stage.prod[0].invoke_url : "Lambda not deployed"
}

output "api_url" {
  description = "Active API URL (custom domain if enabled, else default)"
  value       = var.custom_domain_enabled ? "https://${var.api_subdomain}" : (local.lambda_enabled ? aws_api_gateway_stage.prod[0].invoke_url : "Lambda not deployed")
}

output "lambda_function_name" {
  description = "App Lambda function name"
  value       = local.lambda_enabled ? aws_lambda_function.app[0].function_name : "Not deployed — set image_uri"
}

output "lambda_migrate_function_name" {
  description = "Migration Lambda function name"
  value       = local.lambda_enabled ? aws_lambda_function.migrate[0].function_name : "Not deployed — set image_uri"
}

output "ecr_repository_url" {
  description = "ECR repository URL for building and pushing the container image"
  value       = aws_ecr_repository.app.repository_url
}

output "aurora_endpoint" {
  description = "Aurora cluster writer endpoint (used by Lambda for database connections)"
  value       = aws_rds_cluster.aurora.endpoint
}

output "aurora_cluster_identifier" {
  description = "Aurora cluster identifier"
  value       = aws_rds_cluster.aurora.cluster_identifier
}

output "db_secret_arn" {
  description = "Secrets Manager ARN for Aurora master credentials"
  value       = local.db_secret_arn
}

output "dynamodb_settings_table" {
  description = "DynamoDB table name for runtime settings"
  value       = aws_dynamodb_table.settings.name
}
