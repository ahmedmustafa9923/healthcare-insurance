# ==============================================================================
# Member Data Tier — one isolated set of tables per carrier + line of business
# ==============================================================================

resource "aws_dynamodb_table" "members" {
  name         = "${var.carrier_name}-${var.line_of_business}-members"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "member_id"

  attribute {
    name = "member_id"
    type = "S"
  }
  attribute {
    name = "onboarding_stage"
    type = "S"
  }
  attribute {
    name = "enrolled_date"
    type = "S"
  }
  attribute {
    name = "lapse_year"
    type = "S"
  }
  attribute {
    name = "lapsed_date"
    type = "S"
  }

  # Sparse: only members currently in onboarding (day0 / day7 / day30)
  global_secondary_index {
    name            = "onboarding-index"
    hash_key        = "onboarding_stage"
    range_key       = "enrolled_date"
    projection_type = "ALL"
  }

  # Sparse: only inactive members, partitioned by the year they lapsed
  global_secondary_index {
    name            = "lapsed-index"
    hash_key        = "lapse_year"
    range_key       = "lapsed_date"
    projection_type = "ALL"
  }

  server_side_encryption {
    enabled = true
  }

  point_in_time_recovery {
    enabled = true
  }

  deletion_protection_enabled = true

  tags = {
    Carrier        = var.carrier_name
    LineOfBusiness = var.line_of_business
    DataClass      = "PHI-synthetic"
    ManagedBy      = "Terraform"
  }
}

resource "aws_dynamodb_table" "revenue" {
  name         = "${var.carrier_name}-${var.line_of_business}-revenue"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "year"
  range_key    = "month"

  attribute {
    name = "year"
    type = "S"
  }
  attribute {
    name = "month"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }

  point_in_time_recovery {
    enabled = true
  }

  deletion_protection_enabled = true

  tags = {
    Carrier        = var.carrier_name
    LineOfBusiness = var.line_of_business
    DataClass      = "Financial-synthetic"
    ManagedBy      = "Terraform"
  }
}

resource "aws_dynamodb_table" "leads" {
  name         = "${var.carrier_name}-${var.line_of_business}-leads"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "lead_id"

  attribute {
    name = "lead_id"
    type = "S"
  }
  attribute {
    name = "lead_status"
    type = "S"
  }
  attribute {
    name = "received_date"
    type = "S"
  }

  # Find leads by status (new / contacted / converted), newest first
  global_secondary_index {
    name            = "status-index"
    hash_key        = "lead_status"
    range_key       = "received_date"
    projection_type = "ALL"
  }

  server_side_encryption {
    enabled = true
  }

  point_in_time_recovery {
    enabled = true
  }

  deletion_protection_enabled = true

  tags = {
    Carrier        = var.carrier_name
    LineOfBusiness = var.line_of_business
    DataClass      = "PII-synthetic"
    ManagedBy      = "Terraform"
  }
}

