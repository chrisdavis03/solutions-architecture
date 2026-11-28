# The hosted zone must already exist. Create it outside this repo (or
# hand-create it) and point your registrar at it. This stack never creates a zone.
data "aws_route53_zone" "this" {
  name         = var.domain_name
  private_zone = false
}

locals {
  checkout_fqdn = "checkout.${var.domain_name}"
}

# Health check against the PRIMARY API's execute-api hostname, not checkout.<domain>.
# checkout.<domain> resolves through these very records, so checking it would
# make the check depend on its own answer. Checking the origin directly is the
# only way to measure the primary.
#
# enable_sni = true because execute-api serves only its own certificate and
# needs the SNI hostname during the TLS handshake.
resource "aws_route53_health_check" "primary" {
  count = var.enable_traffic ? 1 : 0

  type              = "HTTPS"
  fqdn              = var.primary_api_hostname
  port              = 443
  resource_path     = "/healthz"
  request_interval  = var.health_check_interval
  failure_threshold = var.health_check_failure_threshold
  measure_latency   = false
  enable_sni        = true

  tags = {
    Name = "mrf-primary-healthz"
  }

  lifecycle {
    precondition {
      condition     = var.primary_api_hostname != ""
      error_message = "primary_api_hostname must be set when enable_traffic is true (use the api_hostname output of terraform/app-primary)."
    }
  }
}

# PRIMARY record: answers while the health check passes.
resource "aws_route53_record" "checkout_primary" {
  count = var.enable_traffic ? 1 : 0

  zone_id         = data.aws_route53_zone.this.zone_id
  name            = local.checkout_fqdn
  type            = "CNAME"
  ttl             = var.record_ttl
  records         = [var.primary_api_hostname]
  set_identifier  = "primary-${var.primary_region}"
  health_check_id = aws_route53_health_check.primary[0].id

  failover_routing_policy {
    type = "PRIMARY"
  }

  lifecycle {
    precondition {
      condition     = var.primary_api_hostname != ""
      error_message = "primary_api_hostname must be set when enable_traffic is true."
    }
  }
}

# SECONDARY record: answers when the primary is unhealthy. No health check is
# attached, so Route 53 always treats it as available. If both regions are down,
# clients still get a (failing) answer rather than NXDOMAIN.
resource "aws_route53_record" "checkout_secondary" {
  count = var.enable_traffic ? 1 : 0

  zone_id        = data.aws_route53_zone.this.zone_id
  name           = local.checkout_fqdn
  type           = "CNAME"
  ttl            = var.record_ttl
  records        = [var.secondary_api_hostname]
  set_identifier = "secondary-${var.secondary_region}"

  failover_routing_policy {
    type = "SECONDARY"
  }

  lifecycle {
    precondition {
      condition     = var.secondary_api_hostname != ""
      error_message = "secondary_api_hostname must be set when enable_traffic is true (use the api_hostname output of terraform/app-secondary)."
    }
  }
}

# Not built in this example. Clients connecting to checkout.<domain> will see a
# TLS certificate mismatch, because execute-api only presents its own
# certificate for the default hostname. Serving checkout.<domain> properly needs
# an ACM certificate in each region plus an API Gateway custom domain name and
# API mapping. Treat that as the next step before any real client uses this host.
