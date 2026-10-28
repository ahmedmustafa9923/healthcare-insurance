# ==============================================================================
# Intake pipeline: data feeds land in S3, S3 notifies SQS, intake-worker loads them
# ==============================================================================

data "aws_caller_identity" "current" {}

# ---------- S3 landing bucket ----------
resource "aws_s3_bucket" "intake" {
  bucket = "healthcare-intake-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_versioning" "intake" {
  bucket = aws_s3_bucket.intake.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "intake" {
  bucket = aws_s3_bucket.intake.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "intake" {
  bucket                  = aws_s3_bucket.intake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "intake" {
  bucket = aws_s3_bucket.intake.id

  rule {
    id     = "expire-processed-feeds"
    status = "Enabled"
    filter {
      prefix = "processed/"
    }
    expiration {
      days = 90
    }
  }

  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

# ---------- SQS: work queue + dead-letter queue ----------
resource "aws_sqs_queue" "intake_dlq" {
  name                      = "healthcare-intake-dlq"
  message_retention_seconds = 1209600 # 14 days to investigate failures
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "intake" {
  name                       = "healthcare-intake"
  visibility_timeout_seconds = 300 # a feed has 5 min to process before retry
  receive_wait_time_seconds  = 20  # long polling: fewer empty calls
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.intake_dlq.arn
    maxReceiveCount     = 5
  })
}

# Only THIS bucket in THIS account may send events to the queue
data "aws_iam_policy_document" "intake_queue" {
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.intake.arn]
    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_s3_bucket.intake.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_sqs_queue_policy" "intake" {
  queue_url = aws_sqs_queue.intake.id
  policy    = data.aws_iam_policy_document.intake_queue.json
}

# New CSVs under incoming/ trigger a queue message
resource "aws_s3_bucket_notification" "intake" {
  bucket = aws_s3_bucket.intake.id

  queue {
    queue_arn     = aws_sqs_queue.intake.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "incoming/"
    filter_suffix = ".csv"
  }

  depends_on = [aws_sqs_queue_policy.intake]
}

# Anything in the DLQ = a feed failed 5 times → email you
resource "aws_cloudwatch_metric_alarm" "intake_dlq" {
  alarm_name          = "healthcare-intake-dlq-not-empty"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.intake_dlq.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# ---------- intake-worker permissions (EKS Pod Identity) ----------
resource "aws_iam_role" "intake_worker" {
  name               = "healthcare-intake-worker"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_trust.json
}

data "aws_iam_policy_document" "intake_worker" {
  statement {
    sid       = "ReadAndMoveFeeds"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.intake.arn}/*"]
  }
  statement {
    sid       = "ListFeeds"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.intake.arn]
  }
  statement {
    sid = "ConsumeQueue"
    actions = [
      "sqs:ReceiveMessage", "sqs:DeleteMessage",
      "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes",
    ]
    resources = [aws_sqs_queue.intake.arn]
  }
  statement {
    sid     = "WriteMembersAndLeads"
    actions = ["dynamodb:PutItem", "dynamodb:BatchWriteItem", "dynamodb:GetItem"]
    resources = flatten([
      for m in local.carrier_stacks : [m.members_table_arn, m.leads_table_arn]
    ])
  }
}

resource "aws_iam_role_policy" "intake_worker" {
  name   = "intake-pipeline"
  role   = aws_iam_role.intake_worker.id
  policy = data.aws_iam_policy_document.intake_worker.json
}

resource "aws_eks_pod_identity_association" "intake_worker" {
  cluster_name    = module.eks.cluster_name
  namespace       = "intake"
  service_account = "intake-worker"
  role_arn        = aws_iam_role.intake_worker.arn
}

output "intake_bucket" {
  value = aws_s3_bucket.intake.bucket
}

output "intake_queue_url" {
  value = aws_sqs_queue.intake.url
}
