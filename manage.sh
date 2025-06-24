#!/usr/bin/env zsh
set -euo pipefail

# --- Colors ---
export RED=$'\033[0;31m'
export GREEN=$'\033[0;32m'
export YELLOW=$'\033[0;33m'
export BLUE=$'\033[0;34m'
export MAGENTA=$'\033[0;35m'
export CYAN=$'\033[0;36m'
export BOLD=$'\033[1m'
export RESET=$'\033[0m'

# --- Configuration ---
DEFAULT_SCHEMA_PATH="app/infrastructure/database/schema.prisma"
SCHEMA_PATH="${SCHEMA_PATH:-$DEFAULT_SCHEMA_PATH}" # Allow SCHEMA_PATH to be overridden by env var

# --- Helper Functions ---

# Function to print a colorful header
print_header() {
  echo "${BOLD}${CYAN}==== Python Project Utility Script ====${RESET}"
}

# Function to print a success message
print_success() {
  echo "${GREEN}✔ $1${RESET}"
}

# Function to print an error message
print_error() {
  echo "${RED}✖ $1${RESET}" >&2
}

# Function to print a warning message
print_warning() {
  echo "${YELLOW}▲ $1${RESET}"
}

# Function to check for a command's existence
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# --- Core Functions ---

# Usage information
usage() {
  print_header
  echo "${BOLD}${BLUE}Usage:${RESET} $(basename "$0") {clean|lint|format|sec|test|test-cov|db-generate|db-migrate|db-deploy|db-reset} [--schema path]"
  echo ""
  echo "  ${YELLOW}clean${RESET}       Remove Python/build/test caches and logs"
  echo "  ${YELLOW}lint${RESET}        Lint the codebase using Ruff and MyPy"
  echo "  ${YELLOW}format${RESET}      Format Python code and Prisma schema"
  echo "  ${YELLOW}sec${RESET}         Check application for security vulnerabilities"
  echo "  ${YELLOW}test${RESET}        Run all tests without coverage"
  echo "  ${YELLOW}test-cov${RESET}    Run all tests with coverage"
  echo "  ${YELLOW}db-generate${RESET} Generate Prisma client (schema: ${SCHEMA_PATH})"
  echo "  ${YELLOW}db-migrate${RESET}  Run Prisma migrations (schema: ${SCHEMA_PATH})"
  echo "  ${YELLOW}db-deploy${RESET}   Deploy Prisma migrations (schema: ${SCHEMA_PATH})"
  echo "  ${YELLOW}db-reset${RESET}    Reset Prisma database (schema: ${SCHEMA_PATH})"
  echo ""
  echo "  ${BOLD}${BLUE}Options:${RESET}"
  echo "    ${BOLD}--schema <path>${RESET}  Override the default Prisma schema path (${DEFAULT_SCHEMA_PATH})"
  echo "                     Can also be set via the SCHEMA_PATH environment variable."
  exit 1
}

# Clean function
clean() {
  echo "${BOLD}${BLUE}🗑️ Cleaning up cache and log files...${RESET}"

  local items_removed=0

  # Helper to remove items
  remove_items() {
    local type=$1
    local name=$2
    echo "${YELLOW}  - Removing $name $type(s)...${RESET}"
    local found_items=()
    while IFS= read -r -d '' item; do
      # shellcheck disable=SC2179
      found_items+="$item"
    done < <(find . -type "$type" -name "$name" -print0)

    if [[ ${#found_items[@]} -gt 0 ]]; then
      ((items_removed++))
      for item in "${found_items[@]}"; do
        rm -rf "$item"
        echo "    Removed: ${item}"
      done
    else
      echo "    No $name $type(s) found."
    fi
  }

  remove_items d ".mypy_cache"
  remove_items d ".pytest_cache"
  remove_items d "__pycache__"
  remove_items d "htmlcov"
  remove_items f ".coverage"
  remove_items d ".ruff_cache"
  remove_items f "*.log"

  if [[ "$items_removed" -gt 0 ]]; then
    print_success "Cleanup complete. ${items_removed} types of items removed."
  else
    print_success "Cleanup complete. No relevant cache or log files found."
  fi
}

# Database functions
db_command() {
  local cmd_name="$1"
  shift
  local prisma_args=("$@")

  echo "${BOLD}${MAGENTA}⚙️ Running Prisma $cmd_name (schema: ${SCHEMA_PATH})...${RESET}"

  if command_exists prisma; then
    if prisma "${prisma_args[@]}" --schema "${SCHEMA_PATH}"; then
      print_success "Prisma $cmd_name completed successfully."
    else
      print_error "Prisma $cmd_name failed."
      exit 1
    fi
  else
    print_error "prisma CLI not found. Please install it first to run database commands."
    exit 1
  fi
}

db_generate() {
  db_command "client generation" "generate"
}

db_migrate() {
  db_command "migrations" "migrate" "dev" "--create-only"
}

db_deploy() {
  db_command "deployment" "migrate" "deploy"
}

db_reset() {
  db_command "database reset" "migrate" "reset" "--force"
}

# Format code
format_code() {
  echo "${BOLD}${BLUE}✨ Formatting Python code with Ruff and AutoFlake...${RESET}"
  if command_exists autoflake && command_exists ruff; then
    autoflake --in-place --recursive .
    ruff format .
    print_success "Python code formatting complete."
  else
    print_warning "autoflake or ruff not found. Skipping Python code formatting."
  fi

  echo "${BOLD}${BLUE}✨ Formatting Prisma schema with Prisma CLI...${RESET}"
  if command_exists prisma; then
    if prisma format --schema "${SCHEMA_PATH}"; then
      print_success "Prisma schema formatting complete."
    else
      print_error "Prisma schema formatting failed."
    fi
  else
    print_warning "prisma CLI not found. Skipping Prisma schema formatting."
  fi
}

# Lint code
lint_code() {
  echo "${BOLD}${BLUE}🔎 Linting codebase with Ruff and MyPy...${RESET}"

  local lint_errors=0

  # Run Ruff
  echo "${CYAN}--- Running Ruff checks ---${RESET}"
  if command_exists ruff; then
    if ruff check . --fix --unsafe-fixes; then
      print_success "Ruff checks passed."
    else
      print_error "Ruff found issues."
      lint_errors=1
    fi
  else
    print_warning "ruff not found. Skipping Ruff checks."
  fi

  # Run MyPy
  echo "${CYAN}--- Running MyPy checks ---${RESET}"
  if command_exists mypy; then
    if mypy app; then # Assuming 'app' is your main application directory for type checking
      print_success "MyPy type checks passed."
    else
      print_error "MyPy found type errors."
      lint_errors=1
    fi
  else
    print_warning "mypy not found. Skipping MyPy checks."
  fi

  if [[ "$lint_errors" -eq 0 ]]; then
    print_success "All linting and type checks complete. No issues found."
  else
    print_error "Linting and type checking completed with errors."
    exit 1
  fi
}

# Security check
sec_check() {
  echo "${BOLD}${BLUE}🔒 Checking application security with Bandit...${RESET}"
  if command_exists bandit; then
    if bandit -r app; then
      print_success "Security check complete. No vulnerabilities found."
    else
      print_error "Security check completed with potential vulnerabilities."
    fi
  else
    print_warning "bandit not found. Skipping security checks."
  fi
}

# Test functions
run_tests() {
  local test_type="$1"
  local pytest_args=("$@")
  shift
  echo "${BOLD}${BLUE}🧪 Running tests (${test_type})...${RESET}"
  if command_exists pytest; then
    if pytest "${pytest_args[@]}"; then
      print_success "Tests (${test_type}) completed successfully."
    else
      print_error "Tests (${test_type}) failed."
      exit 1
    fi
  else
    print_error "pytest not found. Please install it to run tests."
    exit 1
  fi
}

test_no_cov() {
  run_tests "no coverage" "-v" "--tb=short" "--no-cov"
}

test_with_cov() {
  run_tests "with coverage" "--cov=app" "--cov-report=html:app/static/htmlcov" "--cov-report=term-missing:skip-covered" "--cov-fail-under=80" "-v"
}

# --- Argument Parsing ---
CMD="${1:-}"

# Check for --schema argument
if [[ $# -ge 2 ]]; then
  if [[ "$2" == "--schema" ]]; then
    if [[ $# -eq 3 ]]; then
      SCHEMA_PATH="$3"
    else
      print_error "Error: --schema requires a path argument."
      usage
    fi
  fi
fi

# --- Main execution ---
if [[ -z "$CMD" ]]; then
  usage
fi

case "$CMD" in
  clean)
    clean
    ;;
  lint)
    lint_code
    ;;
  format)
    format_code
    ;;
  sec)
    sec_check
    ;;
  test)
    test_no_cov
    ;;
  test-cov)
    test_with_cov
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

exit 0
