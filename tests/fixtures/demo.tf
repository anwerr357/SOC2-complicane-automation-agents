# tests/fixtures/demo.tf
# ─────────────────────
# Intentionally misconfigured Terraform file used to validate the Checkov
# scanner runner during development.
#
# Violations seeded here (by design):
#   CKV_AWS_19  → S3 bucket has no server-side encryption  → CC6.7
#   CKV_AWS_18  → S3 bucket has no access logging          → CC7.1
#   CKV_AWS_19  → DynamoDB table has no encryption         → CC6.7
#   CKV_AWS_40  → IAM role uses wildcard Action            → CC6.1 / CC6.6
#   CKV_AWS_7   → KMS key has no key-rotation enabled      → CC6.7

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

# ── S3 bucket — no encryption, no access logging ──────────────────────────
# Expected violations: CKV_AWS_19 (encryption), CKV_AWS_18 (logging)
resource "aws_s3_bucket" "app_data" {
  bucket = "my-app-data-bucket"

  tags = {
    Environment = "production"
    ManagedBy   = "terraform"
  }
  # VIOLATION: no aws_s3_bucket_server_side_encryption_configuration block
  # VIOLATION: no logging { } block
}

# ── DynamoDB table — no encryption ────────────────────────────────────────
# Expected violation: CKV_AWS_119
resource "aws_dynamodb_table" "sessions" {
  name           = "app-sessions"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "session_id"

  attribute {
    name = "session_id"
    type = "S"
  }

  # VIOLATION: server_side_encryption block is absent
}

# ── IAM role — wildcard permissions ──────────────────────────────────────
# Expected violation: CKV_AWS_40 / CKV_AWS_274
resource "aws_iam_role_policy" "app_policy" {
  name = "app-overprivileged-policy"
  role = "app-role"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        # VIOLATION: wildcard Action grants every AWS API call
        Action   = "*"
        Resource = "*"
      }
    ]
  })
}

# ── KMS key — no key rotation ─────────────────────────────────────────────
# Expected violation: CKV_AWS_7
resource "aws_kms_key" "app_key" {
  description = "Application encryption key"
  # VIOLATION: enable_key_rotation defaults to false
}

# ── Correctly configured resource (should PASS) ───────────────────────────
# RDS instance with encryption enabled — no violation expected
resource "aws_db_instance" "main" {
  identifier        = "app-db"
  engine            = "postgres"
  engine_version    = "16.1"
  instance_class    = "db.t3.micro"
  allocated_storage = 20
  username          = "appuser"
  password          = "change-me-in-secrets-manager"

  storage_encrypted = true    # CC6.7 — PASS
  skip_final_snapshot = true
}
