#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Backend lint, typecheck, and pytest"
cd "$ROOT_DIR/backend"
.venv/bin/ruff check app tests
.venv/bin/mypy app
.venv/bin/pytest -v

echo "==> Frontend tests, typecheck, lint, and production build"
cd "$ROOT_DIR/frontend"
npm test
npm run typecheck
npm run lint
npm run build
