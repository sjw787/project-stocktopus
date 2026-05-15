#!/usr/bin/env bash
# Build and push the Stocktopus Lambda container image to ECR.
#
# Usage: ./deploy/build.sh [environment] [aws-region] [aws-account-id]
# Stdout: the full ECR image URI with the git SHA tag (suitable for capture)
set -euo pipefail

ENVIRONMENT="${1:-prod}"
AWS_REGION="${2:-us-east-1}"
AWS_ACCOUNT_ID="${3:-$(aws sts get-caller-identity --query Account --output text)}"

ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/stocktopus-${ENVIRONMENT}"
IMAGE_TAG="$(git rev-parse --short HEAD)"

echo "=== Authenticating with ECR ===" >&2
aws ecr get-login-password --region "${AWS_REGION}" | \
  docker login --username AWS --password-stdin \
    "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com" >&2

echo "=== Building Docker image (linux/arm64) ===" >&2
docker build --platform linux/arm64 --provenance=false \
  -f deploy/Dockerfile.backend \
  -t "stocktopus:${IMAGE_TAG}" \
  . >&2

echo "=== Tagging and pushing ===" >&2
docker tag "stocktopus:${IMAGE_TAG}" "${ECR_REPO}:${IMAGE_TAG}"
docker tag "stocktopus:${IMAGE_TAG}" "${ECR_REPO}:latest"
docker push "${ECR_REPO}:${IMAGE_TAG}" >&2
docker push "${ECR_REPO}:latest" >&2

# Emit only the full image URI to stdout so callers can capture it
echo "${ECR_REPO}:${IMAGE_TAG}"
