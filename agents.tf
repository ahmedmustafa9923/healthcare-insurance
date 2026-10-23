# ==============================================================================
# Agent platform: shared settings and secrets
# ==============================================================================

# Container for the FRED market-data API key.
# The VALUE is set outside Terraform (CLI) so it never lands in state or Git.
resource "aws_secretsmanager_secret" "fred_api_key" {
  name        = "healthcare/agents/fred-api-key"
  description = "FRED API key used by market-data-mcp"
}

output "fred_secret_arn" {
  value = aws_secretsmanager_secret.fred_api_key.arn
}

