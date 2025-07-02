#!/usr/bin/env zsh
set -euo pipefail

#===============================================================================
# Python Project Utility Script
# Enhanced version with improved output formatting and visual appeal
#===============================================================================

# Color definitions with consistent naming
readonly RED=$'\033[0;31m'
readonly GREEN=$'\033[0;32m'
readonly YELLOW=$'\033[0;33m'
readonly BLUE=$'\033[0;34m'
readonly MAGENTA=$'\033[0;35m'
readonly CYAN=$'\033[0;36m'
readonly BOLD=$'\033[1m'
readonly DIM=$'\033[2m'
readonly RESET=$'\033[0m'

# Additional formatting characters for enhanced output
readonly CHECK_MARK="${GREEN}✓${RESET}"
readonly CROSS_MARK="${RED}✗${RESET}"
readonly ARROW="${BLUE}→${RESET}"
readonly SEPARATOR="═══════════════════════════════════════════════════════════════════════════════"

# Configuration
readonly DEFAULT_SCHEMA_PATH="app/infrastructure/database/schema.prisma"
# shellcheck disable=SC2155
readonly SCRIPT_NAME="$(basename "$0")"

#===============================================================================
# Utility Functions
#===============================================================================

# Enhanced banner with better visual separation
print_banner() {
  echo ""
  echo "${BOLD}${CYAN}${SEPARATOR}${RESET}"
  echo "${BOLD}${CYAN}║                    Python Project Utility Script                    ║${RESET}"
  echo "${BOLD}${CYAN}${SEPARATOR}${RESET}"
  echo ""
}

# Status message with consistent formatting
print_status() {
  local message="$1"
  local color="${2:-$BLUE}"
  printf "${BOLD}${color}[INFO]${RESET} %s\n" "$message"
}

# Success message with checkmark
print_success() {
  local message="$1"
  printf "${CHECK_MARK} ${GREEN}%s${RESET}\n" "$message"
}

# Error message with cross mark
print_error() {
  local message="$1"
  printf "${CROSS_MARK} ${RED}%s${RESET}\n" "$message" >&2
}

# Warning message with consistent formatting
print_warning() {
  local message="$1"
  printf "${YELLOW}[WARN]${RESET} %s\n" "$message"
}

# Section separator for better visual organization
print_section() {
  local title="$1"
  echo ""
  echo "${BOLD}${BLUE}▼ ${title}${RESET}"
  echo "${DIM}${BLUE}────────────────────────────────────────────────────────────────────────────${RESET}"
}

# Command execution with enhanced feedback
execute_command() {
  local cmd="$1"
  local description="$2"
  local success_msg="$3"
  local error_msg="$4"

  print_status "Executing: ${description}"

  if eval "$cmd"; then
    print_success "$success_msg"
    return 0
  else
    print_error "$error_msg"
    return 1
  fi
}

#===============================================================================
# Main Functions
#===============================================================================

usage() {
  print_banner
  echo "${BOLD}${BLUE}USAGE:${RESET}"
  printf "  %s ${YELLOW}<command>${RESET} [${DIM}--schema <path>${RESET}]\n\n" "$SCRIPT_NAME"

  echo "${BOLD}${BLUE}AVAILABLE COMMANDS:${RESET}"
  echo ""
  printf "  ${YELLOW}%-12s${RESET} ${ARROW} %s\n" "clean" "Remove Python/build/test caches and logs"
  printf "  ${YELLOW}%-12s${RESET} ${ARROW} %s\n" "lint" "Lint the codebase using Ruff and MyPy"
  printf "  ${YELLOW}%-12s${RESET} ${ARROW} %s\n" "format" "Format Python code and Prisma schema"
  printf "  ${YELLOW}%-12s${RESET} ${ARROW} %s\n" "sec" "Check application for security vulnerabilities"
  printf "  ${YELLOW}%-12s${RESET} ${ARROW} %s\n" "test" "Run all tests without coverage"
  printf "  ${YELLOW}%-12s${RESET} ${ARROW} %s\n" "test-cov" "Run all tests with coverage reporting"

  echo ""
  echo "${BOLD}${MAGENTA}DATABASE COMMANDS:${RESET}"
  printf "  ${YELLOW}%-12s${RESET} ${ARROW} %s\n" "db-generate" "Generate Prisma client"
  printf "  ${YELLOW}%-12s${RESET} ${ARROW} %s\n" "db-migrate" "Run Prisma migrations"
  printf "  ${YELLOW}%-12s${RESET} ${ARROW} %s\n" "db-deploy" "Deploy Prisma migrations"
  printf "  ${YELLOW}%-12s${RESET} ${ARROW} %s\n" "db-reset" "Reset Prisma database"

  echo ""
  echo "${BOLD}${BLUE}SCHEMA CONFIGURATION:${RESET}"
  echo "  Current schema path: ${CYAN}${SCHEMA_PATH}${RESET}"
  echo ""
  echo "${DIM}Override schema path by:${RESET}"
  echo "  ${DIM}• Setting SCHEMA_PATH environment variable${RESET}"
  echo "  ${DIM}• Using --schema <path> flag${RESET}"
  echo ""

  exit 1
}

clean() {
  print_section "Cleanup Operations"

  remove_items() {
    local type="$1"
    local name="$2"
    local description="$3"

    print_status "Removing ${description}..."

    if find . -type "$type" -name "$name" -print0 2>/dev/null | xargs -0 rm -rf 2>/dev/null; then
      print_success "${description} removed successfully"
    else
      print_warning "No ${description} found or already clean"
    fi
  }

  remove_items "d" ".mypy_cache" "MyPy cache directories"
  remove_items "d" ".pytest_cache" "Pytest cache directories"
  remove_items "d" "__pycache__" "Python cache directories"
  remove_items "d" "htmlcov" "HTML coverage directories"
  remove_items "f" ".coverage" "coverage data files"
  remove_items "d" ".ruff_cache" "Ruff cache directories"
  remove_items "f" "*.log" "log files"

  echo ""
  print_success "Cleanup completed successfully!"
}

check_prisma_cli() {
  if ! command -v prisma >/dev/null 2>&1; then
    print_error "Prisma CLI not found. Please install it first:"
    echo "  ${DIM}npm install -g prisma${RESET}"
    return 1
  fi
  return 0
}

db_generate() {
  print_section "Prisma Client Generation"

  if ! check_prisma_cli; then
    exit 1
  fi

  print_status "Schema path: ${CYAN}${SCHEMA_PATH}${RESET}"

  execute_command \
    "prisma generate --schema '${SCHEMA_PATH}'" \
    "Generating Prisma client" \
    "Prisma client generated successfully!" \
    "Failed to generate Prisma client"
}

db_migrate() {
  print_section "Database Migration"

  if ! check_prisma_cli; then
    exit 1
  fi

  print_status "Schema path: ${CYAN}${SCHEMA_PATH}${RESET}"

  execute_command \
    "prisma migrate dev --schema '${SCHEMA_PATH}' --create-only" \
    "Running database migrations" \
    "Database migrations completed successfully!" \
    "Database migration failed"
}

db_deploy() {
  print_section "Migration Deployment"

  if ! check_prisma_cli; then
    exit 1
  fi

  print_status "Schema path: ${CYAN}${SCHEMA_PATH}${RESET}"

  execute_command \
    "prisma migrate deploy --schema '${SCHEMA_PATH}'" \
    "Deploying migrations to database" \
    "Migrations deployed successfully!" \
    "Migration deployment failed"
}

db_reset() {
  print_section "Database Reset"

  if ! check_prisma_cli; then
    exit 1
  fi

  print_warning "This will completely reset your database!"
  print_status "Schema path: ${CYAN}${SCHEMA_PATH}${RESET}"

  execute_command \
    "prisma migrate reset --schema '${SCHEMA_PATH}' --force" \
    "Resetting database" \
    "Database reset completed successfully!" \
    "Database reset failed"
}

format_code() {
  print_section "Code Formatting"

  # Python formatting
  print_status "Formatting Python code with AutoFlake..."
  if command -v autoflake >/dev/null 2>&1; then
    autoflake --in-place --recursive . && print_success "AutoFlake formatting complete"
  else
    print_warning "AutoFlake not found, skipping..."
  fi

  print_status "Formatting Python code with Ruff..."
  if command -v ruff >/dev/null 2>&1; then
    ruff format . && print_success "Ruff formatting complete"
  else
    print_error "Ruff not found. Please install it first."
    return 1
  fi

  # Prisma formatting
  print_status "Formatting Prisma schema..."
  if command -v prisma >/dev/null 2>&1; then
    execute_command \
      "prisma format --schema '${SCHEMA_PATH}'" \
      "Formatting Prisma schema" \
      "Prisma schema formatting complete!" \
      "Prisma schema formatting failed"
  else
    print_warning "Prisma CLI not found. Skipping schema formatting."
  fi

  echo ""
  print_success "All formatting operations completed!"
}

run_linting() {
  print_section "Code Linting"

  # Ruff linting
  print_status "Running Ruff linter..."
  if execute_command \
    "ruff check . --fix --unsafe-fixes" \
    "Linting with Ruff" \
    "Ruff linting completed successfully!" \
    "Ruff linting found issues"; then
    echo ""
  fi

  # MyPy type checking
  print_status "Running MyPy type checker..."
  execute_command \
    "mypy app" \
    "Type checking with MyPy" \
    "MyPy type checking passed!" \
    "MyPy found type issues"
}

run_security_check() {
  print_section "Security Analysis"

  execute_command \
    "bandit -r app" \
    "Scanning for security issues with Bandit" \
    "Security scan completed - no issues found!" \
    "Security issues detected!"
}

run_tests() {
  print_section "Test Execution"

  execute_command \
    "pytest -v --tb=short --no-cov" \
    "Running test suite" \
    "All tests passed successfully!" \
    "Some tests failed"
}

run_tests_with_coverage() {
  print_section "Test Execution with Coverage"

  execute_command \
    "pytest --cov=app --cov-report=html:app/static/htmlcov --cov-report=term-missing:skip-covered --cov-fail-under=80 -v" \
    "Running tests with coverage analysis" \
    "Tests completed with coverage report generated!" \
    "Tests failed or coverage below threshold"

  echo ""
  print_status "Coverage report available at: ${CYAN}app/static/htmlcov/index.html${RESET}"
}

#===============================================================================
# Main Script Logic
#===============================================================================

main() {
  # Parse arguments
  local cmd="${1:-}"
  SCHEMA_PATH="${SCHEMA_PATH:-$DEFAULT_SCHEMA_PATH}"

  # Handle schema path override
  if [[ $# -eq 3 && "$2" == "--schema" ]]; then
    SCHEMA_PATH="$3"
  fi

  # Show usage if no command provided
  if [[ $# -lt 1 ]]; then
    usage
  fi

  # Display banner
  print_banner

  # Execute command
  case "$cmd" in
    clean)
      clean
      ;;
    lint)
      run_linting
      ;;
    format)
      format_code
      ;;
    sec)
      run_security_check
      ;;
    test)
      run_tests
      ;;
    test-cov)
      run_tests_with_coverage
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
      print_error "Unknown command: $cmd"
      echo ""
      usage
      ;;
  esac

  echo ""
  print_success "Operation completed successfully!"
  echo ""
}

# Execute main function with all arguments
main "$@"
