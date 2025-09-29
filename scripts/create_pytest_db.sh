#!/bin/bash
set -e

# Navigate to the parent directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." &> /dev/null && pwd )"
cd $SCRIPT_DIR

# Source .env file if it exists
if [ ! -f .env ]; then
    echo "Error: .env file not found"
    exit 1
fi

source .env

# Check if required env vars are set
if [ -z "${DOCENT_PG_USER}" ] || [ -z "${DOCENT_PG_PASSWORD}" ]; then
    echo "Error: DOCENT_PG_USER and DOCENT_PG_PASSWORD must be set in .env"
    exit 1
fi

docker exec -e PGPASSWORD="${DOCENT_PG_PASSWORD}" -i docent_postgres \
    psql -U "${DOCENT_PG_USER}" -d postgres \
    -c "CREATE DATABASE _pytest_docent_test;" \
    -c "\c _pytest_docent_test" \
    -c "CREATE EXTENSION IF NOT EXISTS vector;"
