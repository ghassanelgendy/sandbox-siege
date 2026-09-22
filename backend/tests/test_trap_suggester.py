"""Heuristic trap suggestions from imported Terraform (PRD 8.3)."""

from siege.scenarios.loader import _from_dict
from siege.trap_suggester import suggest_traps


def test_suggests_one_trap_per_recognized_resource():
    tf = '''
resource "aws_iam_role" "deploy" {
  name = "prod-deploy-role"
}
resource "aws_kms_key" "db_key" {
  description = "prod db key"
}
resource "aws_security_group" "web" {
  name = "web-sg"
}
resource "aws_lambda_function" "processor" {
  function_name = "prod-processor"
}
'''
    suggestions, unmapped = suggest_traps(tf)
    types = {s.resource_type for s in suggestions}
    assert "aws_iam_role" in types
    assert "aws_kms_key" in types
    assert "aws_security_group" in types
    assert len(unmapped) == 1 and unmapped[0].resource_type == "aws_lambda_function"


def test_non_critical_rds_and_non_prod_bucket_are_not_suggested():
    tf = '''
resource "aws_db_instance" "dev_db" {
  engine = "postgres"
  tags = { tier = "dev" }
}
resource "aws_s3_bucket" "scratch" {
}
'''
    suggestions, _ = suggest_traps(tf)
    assert suggestions == []


def test_accepted_suggestion_loads_as_a_valid_scenario():
    tf = '''
resource "aws_iam_role" "deploy" {
  name = "prod-deploy-role"
}
'''
    suggestions, _ = suggest_traps(tf)
    assert len(suggestions) == 1
    scenario = _from_dict(suggestions[0].scenario_data)
    assert scenario.seed["iam_roles"][0]["name"] == "prod-deploy-role"
    assert scenario.outcome_rules["fail_on"]
