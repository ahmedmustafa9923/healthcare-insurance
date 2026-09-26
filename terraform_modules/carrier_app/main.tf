# 1. Random string to keep bucket names globally unique across AWS
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# 2. HIPAA-isolated S3 Bucket for claim documents
resource "aws_s3_bucket" "carrier_storage" {
  bucket        = "health-app-${var.carrier_name}-${var.line_of_business}-${random_id.bucket_suffix.hex}"
  force_destroy = true

  tags = {
    Carrier        = var.carrier_name
    LineOfBusiness = var.line_of_business
    ManagedBy      = "Terraform"
  }
}

# 3. Encrypt data at rest (Crucial for HIPAA compliance)
resource "aws_s3_bucket_server_side_encryption_configuration" "encryption" {
  bucket = aws_s3_bucket.carrier_storage.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# 4. Strict Public Access Block (Locks down data from the public web)
resource "aws_s3_bucket_public_access_block" "public_block" {
  bucket = aws_s3_bucket.carrier_storage.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# 5. Dedicated IAM Role for App Security Permissions
resource "aws_iam_role" "app_role" {
  name = "app-execution-role-${var.carrier_name}-${var.line_of_business}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "://amazonaws.com" }
    }]
  })
}

# ==============================================================================
# CloudWatch Monitoring Tier (HIPAA Compliant Logging)
# ==============================================================================

resource "aws_cloudwatch_log_group" "carrier_log_group" {
  name              = "/aws/ecs/${var.carrier_name}-${var.line_of_business}"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_stream" "carrier_stream" {
  name           = "app-runtime-core"
  log_group_name = aws_cloudwatch_log_group.carrier_log_group.name
}

resource "aws_cloudwatch_log_metric_filter" "error_filter" {
  name           = "${var.carrier_name}-${var.line_of_business}-error-filter"
  pattern        = "ERROR"
  log_group_name = aws_cloudwatch_log_group.carrier_log_group.name

  metric_transformation {
    name      = "ErrorCount"
    namespace = "Carrier/Applications/${var.carrier_name}"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "application_error_alarm" {
  alarm_name          = "critical-error-alarm-${var.carrier_name}-${var.line_of_business}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = aws_cloudwatch_log_metric_filter.error_filter.metric_transformation.name
  namespace           = aws_cloudwatch_log_metric_filter.error_filter.metric_transformation.namespace
  period              = "300"
  statistic           = "Sum"
  threshold           = "5"
  actions_enabled     = false
}
