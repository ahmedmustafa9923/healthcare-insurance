# ==============================================================================
# GitHub Actions -> AWS with OIDC: no stored keys.
# github-plan  : READ ONLY, used by pull requests (a PR cannot change AWS)
# github-apply : WRITE, only from the "production" GitHub environment (human approval)
# ==============================================================================

variable "github_repo" {
  description = "GitHub repository allowed to assume the CI roles (owner/name)"
  type        = string
  default     = "ahmedmustafa9923/healthcare-insurance"
}

variable "tf_state_bucket" {
  description = "S3 bucket holding Terraform state (created outside Terraform)"
  type        = string
  default     = "healthcare-insurance-tfstate-308281188883"
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

# ---------- trust policies: WHICH workflow runs may assume each role ----------
data "aws_iam_policy_document" "github_plan_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:pull_request"]
    }
  }
}

data "aws_iam_policy_document" "github_apply_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:environment:production"]
    }
  }
}

# ---------- github-plan: read-only + state lock ----------
resource "aws_iam_role" "github_plan" {
  name                 = "healthcare-github-plan"
  assume_role_policy   = data.aws_iam_policy_document.github_plan_trust.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "github_plan_readonly" {
  role       = aws_iam_role.github_plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

data "aws_iam_policy_document" "github_plan_state" {
  statement {
    sid       = "ReadStateAndTakeLock"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["arn:aws:s3:::${var.tf_state_bucket}/healthcare-insurance/*"]
  }
  statement {
    sid       = "ListStateBucket"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.tf_state_bucket}"]
  }
}

resource "aws_iam_role_policy" "github_plan_state" {
  name   = "terraform-state-lock"
  role   = aws_iam_role.github_plan.id
  policy = data.aws_iam_policy_document.github_plan_state.json
}

# ---------- github-apply: write, gated by the production environment ----------
resource "aws_iam_role" "github_apply" {
  name                 = "healthcare-github-apply"
  assume_role_policy   = data.aws_iam_policy_document.github_apply_trust.json
  max_session_duration = 3600
}

# LEARNING-ACCOUNT SHORTCUT: broad rights so CI can apply anything in this stack.
# Production would replace this with a scoped policy.
resource "aws_iam_role_policy_attachment" "github_apply_admin" {
  # checkov:skip=CKV_AWS_274: Accepted risk in this learning account. CI apply role needs broad rights to manage EKS/VPC/IAM; gated by the production environment approval. Follow-up: replace with a scoped policy.
  role       = aws_iam_role.github_apply.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

output "github_plan_role_arn" {
  value = aws_iam_role.github_plan.arn
}

output "github_apply_role_arn" {
  value = aws_iam_role.github_apply.arn
}
