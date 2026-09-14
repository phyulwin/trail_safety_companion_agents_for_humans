#!/bin/bash
# update.sh - Build and replace containers while retaining SQLite and TLS volumes.
set -euo pipefail
cd /opt/trail
chmod 600 .env.production
docker compose --env-file .env.production -f compose.production.yml config --quiet
docker compose --env-file .env.production -f compose.production.yml up -d --build --wait --wait-timeout 180
