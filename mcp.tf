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
# ---------- change requests: every proposed change + decision + before/after (audit) ----------
resource "aws_dynamodb_table" "change_requests" {
  name         = "healthcare-change-requests"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "request_id"

  attribute {
    name = "request_id"
    type = "S"
  }
  attribute {
    name = "status"
    type = "S"
  }
  attribute {
    name = "created_at"
    type = "S"
  }

  global_secondary_index {
    name            = "status-index"
    hash_key        = "status"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  server_side_encryption {
    enabled = true
  }
  point_in_time_recovery {
    enabled = true
  }
  deletion_protection_enabled = true
}

# ---------- member-records-mcp: the ONLY writer of member/lead data ----------
resource "aws_iam_role" "member_records_mcp" {
  name               = "healthcare-member-records-mcp"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_trust.json
}

data "aws_iam_policy_document" "member_records_mcp" {
  statement {
    sid     = "WriteMembersAndLeads"
    actions = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"]
    resources = flatten([
      for m in local.carrier_stacks : [m.members_table_arn, m.leads_table_arn]
    ])
  }
  statement {
    sid     = "ManageChangeRequests"
    actions = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"]
    resources = [
      aws_dynamodb_table.change_requests.arn,
      "${aws_dynamodb_table.change_requests.arn}/index/*",
    ]
  }
}

resource "aws_iam_role_policy" "member_records_mcp" {
  name   = "write-members-via-change-requests"
  role   = aws_iam_role.member_records_mcp.id
  policy = data.aws_iam_policy_document.member_records_mcp.json
}

resource "aws_eks_pod_identity_association" "member_records_mcp" {
  cluster_name    = module.eks.cluster_name
  namespace       = "mcp-tools"
  service_account = "member-records-mcp"
  role_arn        = aws_iam_role.member_records_mcp.arn
}

