data "aws_instance" "healthcare_server" {
  instance_id = "i-0be46f4f125247928" # your instance ID
}

resource "aws_sns_topic" "alerts" {
  name = "healthcare-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = "ahmed.mustafa9923@gmail.com" # your email
}

resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  alarm_name          = "healthcare-server-cpu-high"
  namespace           = "AWS/EC2"
  metric_name         = "CPUUtilization"
  dimensions          = { InstanceId = data.aws_instance.healthcare_server.id }
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 3
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "status_check" {
  alarm_name          = "healthcare-server-status-check"
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed_System"
  dimensions          = { InstanceId = data.aws_instance.healthcare_server.id }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  alarm_actions       = [aws_sns_topic.alerts.arn, "arn:aws:automate:us-east-1:ec2:recover"]
}

resource "aws_cloudwatch_dashboard" "healthcare" {
  dashboard_name = "healthcare-server"
  dashboard_body = jsonencode({
    widgets = [{
      type = "metric", x = 0, y = 0, width = 12, height = 6
      properties = {
        title   = "Healthcare server CPU"
        region  = "us-east-1"
        stat    = "Average"
        period  = 300
        metrics = [["AWS/EC2", "CPUUtilization", "InstanceId", data.aws_instance.healthcare_server.id]]
      }
    }]
  })
}
