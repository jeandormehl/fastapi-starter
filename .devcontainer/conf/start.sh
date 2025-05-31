#!/usr/bin/env zsh
set -euo pipefail

CMD="${1:-}"

poetry config virtualenvs.create false
git config --global --add safe.directory /app

prisma py fetch
./manage.sh db-generate

app() {
  ./manage.sh db-deploy
  python -m app.main
}

worker() {
  python -m app.infrastructure.celery.worker
}

beat() {
  python -m app.infrastructure.celery.beat
}

flower() {
  python -m app.infrastructure.celery.flower
}

case "$CMD" in
  app)
    app
    ;;
  worker)
    worker
    ;;
  beat)
    beat
    ;;
  flower)
    flower
    ;;
esac
