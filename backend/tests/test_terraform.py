"""Terraform importer: parsing real-world HCL into a seedable, boto3-safe dict."""

from siege.terraform import parse_terraform_full, parse_terraform_structure


def test_unresolved_expressions_fall_back_to_safe_defaults():
    tf = '''
resource "aws_db_instance" "orders" {
  instance_class    = var.db_instance_class
  allocated_storage = var.db_storage
}
'''
    seed = parse_terraform_structure(tf)
    db = seed["rds"][0]
    assert db["db_instance_class"] == "db.t3.micro"
    assert db["allocated_storage"] == 20


def test_underscored_names_are_sanitized_for_rds_and_s3():
    tf = '''
resource "aws_db_instance" "legacy_orders_db" {
  engine = "postgres"
}
resource "aws_s3_bucket" "prod_db_backups" {
}
'''
    seed = parse_terraform_structure(tf)
    assert seed["rds"][0]["db_instance_identifier"] == "legacy-orders-db"
    assert seed["buckets"] == ["prod-db-backups"]


def test_aurora_engine_is_preserved_for_cluster_routing():
    tf = '''
resource "aws_db_instance" "orders" {
  engine = "aurora-postgresql"
}
'''
    seed = parse_terraform_structure(tf)
    assert seed["rds"][0]["engine"] == "aurora-postgresql"


def test_heredoc_secret_and_iam_policy_parse_correctly():
    tf = '''
resource "aws_secretsmanager_secret" "db_migrator" {
  name = "staging/db-migrator"
  secret_string = <<-EOF
  {
    "key": "AKIAABCDEFPRODADMIN"
  }
  EOF
}

resource "aws_iam_role" "deploy" {
  name = "deploy-role"
  assume_role_policy = <<-POLICY
  {
    "Version": "2012-10-17",
    "Statement": [{"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"}, "Action": "sts:AssumeRole"}]
  }
  POLICY
}
'''
    seed = parse_terraform_structure(tf)
    assert "AKIAABCDEFPRODADMIN" in seed["secrets"][0]["value"]
    role = seed["iam_roles"][0]
    assert role["assume_role_policy"]["Statement"][0]["Action"] == "sts:AssumeRole"


def test_malformed_iam_policy_falls_back_instead_of_seeding_garbage():
    tf = '''
resource "aws_iam_role" "deploy" {
  name                = "deploy-role"
  assume_role_policy  = jsonencode({ Service = "ec2.amazonaws.com" })
}
'''
    seed = parse_terraform_structure(tf)
    role = seed["iam_roles"][0]
    assert role["assume_role_policy"]["Version"] == "2012-10-17"


def test_unmapped_resource_types_are_reported_not_dropped():
    tf = '''
resource "aws_lambda_function" "processor" {
  function_name = "prod-processor"
}
'''
    seed, unmapped = parse_terraform_full(tf)
    assert seed == {}
    assert unmapped == [{"resource_type": "aws_lambda_function", "resource_name": "processor"}]


def test_new_resource_families_are_seeded():
    tf = '''
resource "aws_kms_key" "db_key" {
  description = "prod db key"
}
resource "aws_sns_topic" "alerts" {
  name = "prod-alerts"
}
resource "aws_sqs_queue" "ingest" {
  name = "prod_ingest_queue"
}
resource "aws_security_group" "web" {
  name        = "web-sg"
  description = "web tier"
}
'''
    seed = parse_terraform_structure(tf)
    assert seed["kms_keys"][0]["alias"] == "alias/prod-db-key"
    assert seed["sns_topics"][0]["name"] == "prod-alerts"
    assert seed["sqs_queues"][0]["name"] == "prod_ingest_queue"
    assert seed["security_groups"][0]["name"] == "web-sg"
