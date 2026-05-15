#!/usr/bin/env bash
# Invoke the migration Lambda to run Alembic migrations from inside the VPC.
#
# Usage: ./deploy/migrate.sh [environment] [aws-region]
# Must be run after `deploy.sh` (Lambda function must exist).
set -euo pipefail

ENVIRONMENT="${1:-prod}"
AWS_REGION="${2:-us-east-1}"
FUNCTION_NAME="stocktopus-${ENVIRONMENT}-migrate"
LOG_FILE="/tmp/migrate-response-$$.json"

echo "=== Invoking migration Lambda: ${FUNCTION_NAME} ===" >&2
aws lambda invoke \
  --function-name "${FUNCTION_NAME}" \
  --region "${AWS_REGION}" \
  --payload '{}' \
  --cli-binary-format raw-in-base64-out \
  "${LOG_FILE}" >&2

echo "=== Migration response ===" >&2
cat "${LOG_FILE}" >&2
echo "" >&2

# Fail the script if the Lambda returned a function error
if grep -q '"FunctionError"' "${LOG_FILE}" 2>/dev/null || \
   python3 -c "import json,sys; d=json.load(open('${LOG_FILE}')); sys.exit(0 if d.get('status')=='ok' else 1)" 2>/dev/null; then
  :
else
  echo "ERROR: Migration Lambda reported failure" >&2
  rm -f "${LOG_FILE}"
  exit 1
fi

rm -f "${LOG_FILE}"
echo "Migrations complete." >&2
