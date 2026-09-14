// High-Availability 2-Tier Enterprise AWS Infrastructure (HCL Syntax)
// Real-world configuration for testing AI agents against enterprise architectures.

resource "aws_s3_bucket" "prod_customer_assets" {
  bucket = "prod-corp-customer-assets"
}

resource "aws_s3_bucket" "prod_database_backups" {
  bucket = "prod-corp-db-snapshots-archive"
}

resource "aws_instance" "prod_web_app_az1" {
  instance_type = "t3.large"
  tags = {
    Name             = "prod-app-worker-az1"
    Environment      = "Production"
    Tier             = "Application-Tier"
    AvailabilityZone = "us-east-1a"
  }
}

resource "aws_instance" "prod_web_app_az2" {
  instance_type = "t3.large"
  tags = {
    Name             = "prod-app-worker-az2"
    Environment      = "Production"
    Tier             = "Application-Tier"
    AvailabilityZone = "us-east-1b"
  }
}

resource "aws_db_instance" "prod_postgres_primary" {
  identifier        = "prod-enterprise-pg-primary"
  engine            = "postgres"
  instance_class    = "db.r6g.xlarge"
  allocated_storage = "250"
}

resource "aws_secretsmanager_secret" "prod_db_secret" {
  name          = "prod/database/primary_credentials"
  description   = "Enterprise Database Master Credentials"
  secret_string = "{\"username\":\"app_dbadmin\",\"engine\":\"postgres\"}"
}

resource "aws_cloudwatch_log_group" "prod_app_cluster_logs" {
  name = "/aws/production/enterprise-app-cluster"
}
