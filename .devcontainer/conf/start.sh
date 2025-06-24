#!/usr/bin/env zsh
set -euo pipefail

CMD="${1:-}"

./manage.sh db-generate

app() {
  ./manage.sh db-deploy
  python -m app.main
}

worker() {
  local_params=""
  if [[ -n "${ENVIRONMENT:-}" && "$ENVIRONMENT" = "local" ]]; then
    # Add desired parameter(s) here for the local environment
    local_params+="--reload"
  fi

  taskiq worker app.infrastructure.taskiq.worker:app \
    --max-async-tasks 10 \
    --max-prefetch 10 \
    -w 2 \
    --tasks-pattern "**/*_task.py" \
    -fsd \
    --wait-tasks-timeout 30 \
    "${local_params}"
}

scheduler() {
  taskiq scheduler app.infrastructure.taskiq.scheduler:app \
    --tasks-pattern "**/*_task.py" \
    -fsd \
    --skip-first-run
}

case "$CMD" in
  app)
    app
    ;;
  worker)
    worker
    ;;
  scheduler)
    scheduler
    ;;
esac
