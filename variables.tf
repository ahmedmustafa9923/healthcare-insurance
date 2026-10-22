variable "monitored_instance_id" {
  description = "EC2 instance the CloudWatch CPU and status alarms watch"
  type        = string
}

variable "alert_email" {
  description = "Email address that receives SNS alarm notifications"
  type        = string
}
variable "admin_cidr" {
  description = "Workstation public IP (x.x.x.x/32) allowed to reach the EKS API"
  type        = string
}

