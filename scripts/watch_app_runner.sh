#!/bin/bash

set -euo pipefail

usage() {
    cat <<EOF
Usage: $0 <deployment-id> [-f|--filter-pattern <pattern>] [-s|--since <time>]

Tail App Runner application logs for a deployment. The default filter pattern
removes load balancer health checks; any additional filter pattern provided is
appended to the CloudWatch Logs filter pattern.

Options:
  -f, --filter-pattern  CloudWatch Logs filter pattern
  -s, --since           How far back to start (default: 30m)
EOF
    exit "${1:-1}"
}

DEPLOYMENT_ID=""
USER_FILTER=""
SINCE="30m"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--filter-pattern)
            shift
            if [[ $# -eq 0 ]]; then
                echo "Missing filter pattern after -f|--filter-pattern" >&2
                usage
            fi
            USER_FILTER=$1
            shift
            ;;
        -s|--since)
            shift
            if [[ $# -eq 0 ]]; then
                echo "Missing time after -s|--since" >&2
                usage
            fi
            SINCE=$1
            shift
            ;;
        -h|--help)
            usage 0
            ;;
        *)
            if [[ -z "$DEPLOYMENT_ID" ]]; then
                DEPLOYMENT_ID=$1
                shift
            else
                echo "Unexpected argument: $1"
                usage
            fi
            ;;
    esac
done

if [[ -z "$DEPLOYMENT_ID" ]]; then
    usage 1
fi

LOG_GROUP=$(aws logs describe-log-groups --log-group-name-prefix /aws/apprunner | jq -r --arg id "$DEPLOYMENT_ID" '.logGroups[] | select(.logGroupName | contains($id) and contains("application")) | .logGroupName')

if [[ -z "$LOG_GROUP" ]]; then
    echo "Could not find an App Runner application log group for deployment id: $DEPLOYMENT_ID" >&2
    exit 1
fi

CMD=(aws logs tail "$LOG_GROUP")
if [[ -n "$USER_FILTER" ]]; then
    CMD+=(--filter-pattern "$USER_FILTER")
fi
CMD+=(--follow --since="$SINCE")

echo "Running: ${CMD[*]}"
"${CMD[@]}"
