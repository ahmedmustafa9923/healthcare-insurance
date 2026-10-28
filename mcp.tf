# ==============================================================================
# MCP tool servers: each runs on EKS with its own least-privilege Pod Identity role
# ==============================================================================

# ---------- member-data-mcp: READ ONLY ----------
resource "aws_iam_role" "member_data_mcp" {
  name               = "healthcare-member-data-mcp"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_trust.json
}

data "aws_iam_policy_document" "member_data_mcp" {
  statement {
    sid     = "ReadCarrierTables"
    actions = ["dynamodb:GetItem", "dynamodb:Query"]
    resources = flatten([
      for m in local.carrier_stacks : [
        m.members_table_arn, "${m.members_table_arn}/index/*",
        m.leads_table_arn, "${m.leads_table_arn}/index/*",
        m.revenue_table_arn,
      ]
    ])
  }
}

resource "aws_iam_role_policy" "member_data_mcp" {
  name   = "read-carrier-tables"
  role   = aws_iam_role.member_data_mcp.id
  policy = data.aws_iam_policy_document.member_data_mcp.json
}

resource "aws_eks_pod_identity_association" "member_data_mcp" {
  cluster_name    = module.eks.cluster_name
  namespace       = "mcp-tools"
  service_account = "member-data-mcp"
  role_arn        = aws_iam_role.member_data_mcp.arn
}
