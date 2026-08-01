#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT"
export VITE_BASE_PATH="${VITE_BASE_PATH:-/settling-workbench/}"
export VITE_API_URL="${VITE_API_URL:-/settling-workbench-api}"

npm run build --workspace frontend
