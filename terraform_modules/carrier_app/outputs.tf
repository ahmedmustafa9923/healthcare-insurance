output "s3_bucket_name" {
  description = "The name of the generated secure S3 bucket"
  value       = aws_s3_bucket.carrier_storage.id
}

output "iam_role_arn" {
  description = "The ARN of the dedicated application IAM role"
  value       = aws_iam_role.app_role.arn
}


output "members_table_name" {
  description = "DynamoDB members table for this carrier + line of business"
  value       = aws_dynamodb_table.members.name
}

output "members_table_arn" {
  value = aws_dynamodb_table.members.arn
}

output "revenue_table_name" {
  description = "DynamoDB revenue table for this carrier + line of business"
  value       = aws_dynamodb_table.revenue.name
}

output "revenue_table_arn" {
  value = aws_dynamodb_table.revenue.arn
}
