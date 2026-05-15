resource "aws_cognito_user_pool" "main" {
  name = local.name_prefix

  password_policy {
    minimum_length    = 12
    require_uppercase = true
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
  }

  auto_verified_attributes = ["email"]
  username_attributes      = ["email"]
  mfa_configuration        = "OFF"

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  admin_create_user_config {
    allow_admin_create_user_only = true

    invite_message_template {
      email_subject = "Your Stocktopus invitation"
      email_message = "Hi {username}, you've been invited to Stocktopus. Your temporary password is {####}. Sign in at https://stocktopus.samwylock.com and you'll be prompted to set a permanent password."
      sms_message   = "Your Stocktopus username is {username} and temporary password is {####}"
    }
  }

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true
    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  tags = merge(local.component_tags.auth, { Name = local.name_prefix })
}

# Web client (SPA / Amplify frontend) — PKCE code flow, no client secret
resource "aws_cognito_user_pool_client" "web" {
  name         = "${local.name_prefix}-web"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]

  callback_urls = compact([
    "http://localhost:5173/auth/callback",
    var.custom_domain_enabled ? "https://${var.domain_name}/auth/callback" : "",
  ])

  logout_urls = compact([
    "http://localhost:5173",
    var.custom_domain_enabled ? "https://${var.domain_name}" : "",
  ])

  supported_identity_providers = compact([
    "COGNITO",
    var.google_client_id != "" ? "Google" : "",
  ])

  access_token_validity  = 1
  id_token_validity      = 1
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  prevent_user_existence_errors = "ENABLED"
}

resource "aws_cognito_user_pool_domain" "main" {
  domain       = "${var.cognito_domain_prefix}-${var.environment}"
  user_pool_id = aws_cognito_user_pool.main.id
}

output "cognito_hosted_ui_url" {
  description = "Cognito Hosted UI base URL"
  value       = "https://${aws_cognito_user_pool_domain.main.domain}.auth.${var.aws_region}.amazoncognito.com"
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = aws_cognito_user_pool.main.id
}

output "cognito_client_id" {
  description = "Cognito Web App Client ID"
  value       = aws_cognito_user_pool_client.web.id
}

# Google OAuth identity provider — only created when credentials are provided.
# To enable: set google_client_id and google_client_secret in terraform.tfvars,
# then run terraform apply. No frontend changes are needed until you add the button.
resource "aws_cognito_identity_provider" "google" {
  count = var.google_client_id != "" ? 1 : 0

  user_pool_id  = aws_cognito_user_pool.main.id
  provider_name = "Google"
  provider_type = "Google"

  provider_details = {
    client_id        = var.google_client_id
    client_secret    = var.google_client_secret
    authorize_scopes = "openid email profile"
  }

  attribute_mapping = {
    email          = "email"
    email_verified = "email_verified"
    name           = "name"
    username       = "sub"
  }
}
