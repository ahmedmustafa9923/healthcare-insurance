# Unit tests for the carrier_app module.
# Mock providers: runs offline in seconds, needs no AWS account and creates nothing.
# Run from this module's folder:  terraform init && terraform test

mock_provider "aws" {}
mock_provider "random" {}

variables {
  carrier_name     = "test-carrier"
  line_of_business = "personal"
}

run "resources_follow_naming_convention" {
  command = plan

  assert {
    condition     = aws_dynamodb_table.members.name == "test-carrier-personal-members"
    error_message = "Members table must be named <carrier>-<lob>-members."
  }
  assert {
    condition     = aws_dynamodb_table.leads.name == "test-carrier-personal-leads"
    error_message = "Leads table must be named <carrier>-<lob>-leads."
  }
  assert {
    condition     = aws_dynamodb_table.revenue.name == "test-carrier-personal-revenue"
    error_message = "Revenue table must be named <carrier>-<lob>-revenue."
  }
  assert {
    condition     = aws_iam_role.app_role.name == "app-execution-role-test-carrier-personal"
    error_message = "IAM role must be named app-execution-role-<carrier>-<lob>."
  }
}

run "tenant_data_is_protected" {
  command = plan

  assert {
    condition = alltrue([
      aws_dynamodb_table.members.deletion_protection_enabled,
      aws_dynamodb_table.leads.deletion_protection_enabled,
      aws_dynamodb_table.revenue.deletion_protection_enabled,
    ])
    error_message = "Every tenant table must have deletion protection enabled."
  }
  assert {
    condition = alltrue([
      aws_dynamodb_table.members.point_in_time_recovery[0].enabled,
      aws_dynamodb_table.leads.point_in_time_recovery[0].enabled,
      aws_dynamodb_table.revenue.point_in_time_recovery[0].enabled,
    ])
    error_message = "Every tenant table must have point-in-time recovery enabled."
  }
  assert {
    condition = alltrue([
      aws_dynamodb_table.members.server_side_encryption[0].enabled,
      aws_dynamodb_table.leads.server_side_encryption[0].enabled,
      aws_dynamodb_table.revenue.server_side_encryption[0].enabled,
    ])
    error_message = "Every tenant table must be encrypted at rest."
  }
}

run "tenant_bucket_is_private_and_encrypted" {
  command = plan

  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.public_block.block_public_acls,
      aws_s3_bucket_public_access_block.public_block.block_public_policy,
      aws_s3_bucket_public_access_block.public_block.ignore_public_acls,
      aws_s3_bucket_public_access_block.public_block.restrict_public_buckets,
    ])
    error_message = "Tenant buckets must block all public access."
  }
  assert {
    condition     = one(aws_s3_bucket_server_side_encryption_configuration.encryption.rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256"
    error_message = "Tenant buckets must use server-side encryption."
  }
}

run "sparse_indexes_exist_for_onboarding_and_winback" {
  command = plan

  assert {
    condition     = toset([for g in aws_dynamodb_table.members.global_secondary_index : g.name]) == toset(["onboarding-index", "lapsed-index"])
    error_message = "Members table must have onboarding-index and lapsed-index."
  }
}

run "rejects_unknown_line_of_business" {
  command = plan

  variables {
    line_of_business = "commercial"
  }

  expect_failures = [var.line_of_business]
}

run "rejects_badly_formatted_carrier_name" {
  command = plan

  variables {
    carrier_name = "Blue Cross"
  }

  expect_failures = [var.carrier_name]
}
