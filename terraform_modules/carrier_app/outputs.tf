output "s3_bucket_name" {
  description = "The name of the generated secure S3 bucket"
  value       = aws_s3_bucket.carrier_storage.id
}

output "iam_role_arn" {
  description = "The ARN of the dedicated application IAM role"
  value       = aws_iam_role.app_role.arn
}
