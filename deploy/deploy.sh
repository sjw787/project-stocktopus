#!/usr/bin/env bash
# Run Terraform apply for Stocktopus infrastructure and emit outputs.
#
# Usage: ./deploy/deploy.sh <environment> <aws-region> <image-uri>
# Stdout: terraform output -json
set -euo pipefail

ENVIRONMENT="${1:-prod}"
AWS_REGION="${2:-us-east-1}"
IMAGE_URI="${3:-}"

if [[ -z "${IMAGE_URI}" ]]; then
  echo "ERROR: image_uri is required." >&2
  echo "Usage: $0 <environment> <aws-region> <image-uri>" >&2
  exit 1
fi

AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
TF_STATE_BUCKET="stocktopus-tf-state-${AWS_ACCOUNT_ID}"

cd "$(git rev-parse --show-toplevel)/infra"

echo "=== Terraform init ===" >&2
terraform init \
  -backend-config="bucket=${TF_STATE_BUCKET}" \
  -backend-config="key=stocktopus/${ENVIRONMENT}/terraform.tfstate" \
  -backend-config="region=${AWS_REGION}" \
  -input=false \
  -reconfigure >&2

echo "=== Terraform apply ===" >&2
terraform apply \
  -var="environment=${ENVIRONMENT}" \
  -var="aws_region=${AWS_REGION}" \
  -var="image_uri=${IMAGE_URI}" \
  -auto-approve \
  -input=false >&2

echo "=== Outputs ===" >&2
terraform output -json
