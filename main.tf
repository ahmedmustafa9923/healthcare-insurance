
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

resource "aws_security_group" "healthcare_sg" {
  name        = "healthcare-pipeline-sg"
  description = "Allow secure web traffic to our enterprise cluster"

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # In production, swap this with your specific home IP block
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "healthcare_server" {
  ami           = "ami-053b0d53c279acc90" # Verified production baseline for Amazon Linux 2023
  instance_type = "t3.medium"
  key_name      = "GermanDrive"

  vpc_security_group_ids = [aws_security_group.healthcare_sg.id]

  tags = {
    Name    = "Healthcare-Production-Host"
    Project = "healthcare-insurance-pipeline"
  }
}
