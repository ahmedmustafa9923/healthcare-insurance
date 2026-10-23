# ==============================================================================
# Data Seeder: IAM role the seeder pods assume through EKS Pod Identity
# ==============================================================================

locals {
  carrier_stacks = [
    module.blue_cross_personal, module.blue_cross_business,
    module.hartford_personal, module.hartford_business,
    module.all_state_personal, module.all_state_business,
  ]

  # The 12 tables (members + revenue for each provision)
  seed_table_arns = flatten([
    for m in local.carrier_stacks : [m.members_table_arn, m.revenue_table_arn]
  ])
}

# Only EKS Pod Identity may assume this role
data "aws_iam_policy_document" "pod_identity_trust" {
  statement {
    actions = ["sts:AssumeRole", "sts:TagSession"]
    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "data_seeder" {
  name               = "healthcare-data-seeder"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_trust.json
}

# Write-only access to exactly the 12 tables, nothing else
data "aws_iam_policy_document" "data_seeder" {
  statement {
    actions   = ["dynamodb:BatchWriteItem", "dynamodb:PutItem", "dynamodb:DescribeTable"]
    resources = local.seed_table_arns
  }
}

resource "aws_iam_role_policy" "data_seeder" {
  name   = "write-carrier-tables"
  role   = aws_iam_role.data_seeder.id
  policy = data.aws_iam_policy_document.data_seeder.json
}

# Links the K8s service account data-seeder/data-seeder to the IAM role
resource "aws_eks_pod_identity_association" "data_seeder" {
  cluster_name    = module.eks.cluster_name
  namespace       = "data-seeder"
  service_account = "data-seeder"
  role_arn        = aws_iam_role.data_seeder.arn
}

