locals {
  zone_id = (
    var.create_hosted_zone ? aws_route53_zone.main[0].zone_id :
    var.hosted_zone_id
  )
}

resource "aws_route53_zone" "main" {
  count = var.create_hosted_zone ? 1 : 0
  name  = var.domain_name
}

# ACM DNS validation records
resource "aws_route53_record" "cert_validation" {
  for_each = var.custom_domain_enabled && local.zone_id != "" ? {
    for dvo in aws_acm_certificate.api[0].domain_validation_options :
    dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  } : {}

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = local.zone_id
}

# API Gateway custom domain A-record alias
resource "aws_route53_record" "api" {
  count   = var.custom_domain_enabled && local.zone_id != "" ? 1 : 0
  zone_id = local.zone_id
  name    = var.api_subdomain
  type    = "A"

  alias {
    name                   = aws_api_gateway_domain_name.api[0].regional_domain_name
    zone_id                = aws_api_gateway_domain_name.api[0].regional_zone_id
    evaluate_target_health = false
  }
}

output "route53_nameservers" {
  description = "Nameservers to delegate to (needed when create_hosted_zone = true)"
  value       = var.create_hosted_zone ? aws_route53_zone.main[0].name_servers : []
}
