variable "environment" {
  description = "Deployment environment (prod or dev)"
  type        = string
  default     = "prod"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "image_uri" {
  description = "ECR image URI for the Lambda function (set after first ECR push)"
  type        = string
  default     = ""
}

variable "lambda_memory_mb" {
  description = "Lambda memory in MB (larger than typical due to ML/scientific libs)"
  type        = number
  default     = 1024
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout for API Gateway requests (max 29s for HTTP API)"
  type        = number
  default     = 29
}

variable "scheduled_lambda_timeout_seconds" {
  description = "Lambda timeout for EventBridge scheduled tasks"
  type        = number
  default     = 300
}

# ── Networking ────────────────────────────────────────────────────────────────

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

# ── Database ──────────────────────────────────────────────────────────────────

variable "db_name" {
  description = "Aurora database name"
  type        = string
  default     = "stocktopus"
}

variable "db_username" {
  description = "Aurora master username"
  type        = string
  default     = "stocktopus_app"
}

# ── Frontend / Amplify ────────────────────────────────────────────────────────

variable "github_repository" {
  description = "GitHub repository URL for Amplify (e.g. https://github.com/owner/repo)"
  type        = string
  default     = ""
}

variable "github_access_token" {
  description = "GitHub personal access token for Amplify repository access"
  type        = string
  sensitive   = true
  default     = ""
}

variable "github_branch" {
  description = "Branch to deploy via Amplify"
  type        = string
  default     = "main"
}

variable "github_repo_slug" {
  description = "GitHub repo owner/name for OIDC trust policy (e.g. owner/project-stocktopus)"
  type        = string
  default     = ""
}

# ── DNS / TLS ─────────────────────────────────────────────────────────────────

variable "domain_name" {
  description = "Root domain for the app (e.g. stocktopus.samwylock.com)"
  type        = string
  default     = "stocktopus.samwylock.com"
}

variable "api_subdomain" {
  description = "API Gateway custom domain"
  type        = string
  default     = "api.stocktopus.samwylock.com"
}

variable "hosted_zone_id" {
  description = "Existing Route 53 hosted zone ID (leave empty to create a new zone)"
  type        = string
  default     = ""
}

variable "create_hosted_zone" {
  description = "Create a new Route 53 hosted zone for domain_name"
  type        = bool
  default     = true
}

variable "custom_domain_enabled" {
  description = "Enable custom domain mapping (set true after DNS is delegated)"
  type        = bool
  default     = false
}

# ── Auth ──────────────────────────────────────────────────────────────────────

variable "cognito_domain_prefix" {
  description = "Prefix for the Cognito Hosted UI domain"
  type        = string
  default     = "stocktopus-auth"
}

# ── CORS ──────────────────────────────────────────────────────────────────────

variable "cors_origins" {
  description = "Comma-separated allowed CORS origins (e.g. https://stocktopus.samwylock.com)"
  type        = string
  default     = ""
}

# ── Secrets ───────────────────────────────────────────────────────────────────

variable "openai_api_key" {
  description = "OpenAI API key — stored in Secrets Manager"
  type        = string
  sensitive   = true
  default     = ""
}

variable "anthropic_api_key" {
  description = "Anthropic API key — stored in Secrets Manager"
  type        = string
  sensitive   = true
  default     = ""
}

variable "alpaca_api_key" {
  description = "Alpaca API key — stored in Secrets Manager"
  type        = string
  sensitive   = true
  default     = ""
}

variable "alpaca_secret_key" {
  description = "Alpaca secret key — stored in Secrets Manager"
  type        = string
  sensitive   = true
  default     = ""
}

variable "finnhub_api_key" {
  description = "Finnhub API key — stored in Secrets Manager"
  type        = string
  sensitive   = true
  default     = ""
}

variable "newsapi_api_key" {
  description = "NewsAPI API key — stored in Secrets Manager"
  type        = string
  sensitive   = true
  default     = ""
}

variable "google_client_id" {
  description = "Google OAuth 2.0 Client ID for Cognito identity provider (optional)"
  type        = string
  default     = ""
}

variable "google_client_secret" {
  description = "Google OAuth 2.0 Client Secret for Cognito identity provider (optional)"
  type        = string
  sensitive   = true
  default     = ""
}
