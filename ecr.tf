locals {
  apps = ["member-api", "worker", "chat-agent", "board-report", "data-seeder", "intake-worker", "member-data-mcp"]
}

resource "aws_ecr_repository" "apps" {
  for_each             = toset(local.apps)
  name                 = "healthcare/${each.key}"
  image_tag_mutability = "IMMUTABLE" # a tag always means the same image

  image_scanning_configuration {
    scan_on_push = true # CVE scan every pushed image
  }
}

resource "aws_ecr_lifecycle_policy" "keep_recent" {
  for_each   = aws_ecr_repository.apps
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
      action       = { type = "expire" }
    }]
  })
}

