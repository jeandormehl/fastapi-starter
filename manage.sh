#!/usr/bin/env zsh
set -euo pipefail

# colors
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[0;33m'
BLUE=$'\033[0;34m'
MAGENTA=$'\033[0;35m'
CYAN=$'\033[0;36m'
BOLD=$'\033[1m'
RESET=$'\033[0m'

DEFAULT_SCHEMA_PATH="app/infrastructure/database/schema.prisma"

# Banner
echo "${BOLD}${CYAN}==== Python Project Utility Script ====${RESET}"

# Parse arguments
CMD="${1:-}"
SCHEMA_PATH="${SCHEMA_PATH:-$DEFAULT_SCHEMA_PATH}"

if [[ $# -eq 3 && "$2" == "--schema" ]]; then
  SCHEMA_PATH="$3"
fi

function usage() {
  echo "${BOLD}${BLUE}Usage:${RESET} $0 {clean|lint|format|test|test-cov|db-generate|db-migrate|db-deploy|db-reset} [--schema path]"
  echo "  ${YELLOW}clean${RESET}         Remove Python/build/test caches and logs"
  echo "  ${YELLOW}lint${RESET}          Lint the codebase using Ruff"
  echo "  ${YELLOW}format${RESET}        Format Python code and Prisma schema"
  echo "  ${YELLOW}test${RESET}          Run all tests without coverage"
  echo "  ${YELLOW}test-cov${RESET}      Run all tests with coverage"
  echo "  ${YELLOW}db-generate${RESET}   Generate Prisma client (schema: ${SCHEMA_PATH})"
  echo "  ${YELLOW}db-migrate${RESET}    Run Prisma migrations (schema: ${SCHEMA_PATH})"
  echo "  ${YELLOW}db-deploy${RESET}     Deploy Prisma migrations (schema: ${SCHEMA_PATH})"
  echo "  ${YELLOW}db-reset${RESET}      Reset Prisma database (schema: ${SCHEMA_PATH})"
  echo ""
  echo "  You can override the schema path by:"
  echo "    - Setting the SCHEMA_PATH env variable"
  echo "    - Or passing --schema <path> as a second argument"
  exit 1
}

clean() {
  echo "${BOLD}${BLUE}Cleaning up cache and log files...${RESET}"

  remove_items() {
    local type=$1
    local name=$2
    echo "${YELLOW}Removing $name $type(s)...${RESET}"
    find . -type "$type" -name "$name" -print -exec rm -rf {} +
  }

  remove_items d .mypy_cache
  remove_items d .pytest_cache
  remove_items d __pycache__
  remove_items d htmlcov
  remove_items f .coverage
  remove_items d .ruff_cache
  remove_items f '*.log'

  echo "${GREEN}Cleanup complete.${RESET}"
}

db_generate() {
  echo "${BOLD}${MAGENTA}Generating Prisma client (schema: ${SCHEMA_PATH})...${RESET}"
  if command -v prisma >/dev/null 2>&1; then
    prisma generate --schema "${SCHEMA_PATH}" \
      && echo "${GREEN}Prisma client generated successfully.${RESET}" \
      || echo "${RED}Failed to generate Prisma client.${RESET}"
  else
    echo "${RED}prisma CLI not found. Please install it first.${RESET}"
    exit 1
  fi
}

db_migrate() {
  echo "${BOLD}${MAGENTA}Running Prisma migrations (schema: ${SCHEMA_PATH})...${RESET}"
  if command -v prisma >/dev/null 2>&1; then
    prisma migrate dev --schema "${SCHEMA_PATH}" --create-only \
      && echo "${GREEN}Prisma migrations complete.${RESET}" \
      || echo "${RED}Prisma migrations failed.${RESET}"
  else
    echo "${RED}prisma CLI not found. Please install it first.${RESET}"
    exit 1
  fi
}

db_deploy() {
  echo "${BOLD}${MAGENTA}Deploying Prisma migrations (schema: ${SCHEMA_PATH})...${RESET}"
  if command -v prisma >/dev/null 2>&1; then
    prisma migrate deploy --schema "${SCHEMA_PATH}" \
      && echo "${GREEN}Prisma migrations deployed.${RESET}" \
      || echo "${RED}Prisma deployment failed.${RESET}"
  else
    echo "${RED}prisma CLI not found. Please install it first.${RESET}"
    exit 1
  fi
}

db_reset() {
  echo "${BOLD}${MAGENTA}Resetting Prisma database (schema: ${SCHEMA_PATH})...${RESET}"
  if command -v prisma >/dev/null 2>&1; then
    prisma migrate reset --schema "${SCHEMA_PATH}" --force \
      && echo "${GREEN}Prisma database reset.${RESET}" \
      || echo "${RED}Prisma reset failed.${RESET}"
  else
    echo "${RED}prisma CLI not found. Please install it first.${RESET}"
    exit 1
  fi
}

format_code() {
  echo "${BOLD}${BLUE}Formatting Python code with Ruff and AutoFlake...${RESET}"
  autoflake --in-place --recursive .
  ruff format .
  echo "${GREEN}Python formatting complete.${RESET}"

  echo "${BOLD}${BLUE}Formatting Prisma schema with Prisma CLI...${RESET}"
  if command -v prisma >/dev/null 2>&1; then
    prisma format --schema "${SCHEMA_PATH}" \
      && echo "${GREEN}Prisma schema formatting complete.${RESET}" \
      || echo "${RED}Prisma schema formatting failed.${RESET}"
  else
    echo "${YELLOW}Warning: prisma CLI not found. Skipping Prisma schema formatting.${RESET}"
  fi
}

if [[ $# -lt 1 ]]; then
  usage
fi

case "$CMD" in
  clean)
    clean
    ;;
  lint)
    echo "${BOLD}${BLUE}Linting codebase with Ruff...${RESET}"
    ruff check . --fix
    echo "${GREEN}Linting complete.${RESET}"
    ;;
  format)
    format_code
    ;;
  test)
    echo "${BOLD}${BLUE}Running all tests (no coverage)...${RESET}"
    pytest -v --tb=short --no-cov
    echo "${GREEN}Testing complete.${RESET}"
    ;;
  test-cov)
    echo "${BOLD}${BLUE}Running all tests with coverage...${RESET}"
    pytest --cov=app --cov-report=html:app/static/htmlcov --cov-report=term-missing:skip-covered --cov-fail-under=80 -v
    echo "${GREEN}Testing with coverage complete.${RESET}"
    ;;
  db-generate)
    db_generate
    ;;
  db-migrate)
    db_migrate
    ;;
  db-deploy)
    db_deploy
    ;;
  db-reset)
    db_reset
    ;;
  *)
    usage
    ;;
esac
