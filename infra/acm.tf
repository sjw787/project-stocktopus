# ACM certificate for the custom domain.
# Created in us-east-1 for API Gateway and Amplify regardless of stack region.
resource "aws_acm_certificate" "api" {
  count             = var.custom_domain_enabled ? 1 : 0
  domain_name       = var.api_subdomain
  validation_method = "DNS"

  subject_alternative_names = [var.domain_name]

  lifecycle {
    create_before_destroy = true
  }

  tags = merge(local.component_tags.dns, { Name = "${local.name_prefix}-cert" })
}

resource "aws_acm_certificate_validation" "api" {
  count                   = var.custom_domain_enabled ? 1 : 0
  certificate_arn         = aws_acm_certificate.api[0].arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}
