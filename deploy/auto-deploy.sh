#!/bin/sh
# CD: run every minute by the kumbha-backend-deploy systemd timer (deploy/systemd/).
# Pulls new commits on main and redeploys docker-compose.prod.yml when there is one; otherwise
# does nothing. If the new version doesn't come up healthy, the previous image is put back.
# A failed commit is not retried every minute: the next commit is tried instead.
# Logs: journalctl -u kumbha-backend-deploy -f
# Wrapped in main() so the whole file is read before `git merge` can replace it mid-run.
main() {
  set -eu
  cd "$(dirname "$0")/.."

  [ "$(git branch --show-current)" = main ] || { echo "Not on main; skipping deploy" >&2; exit 0; }
  git fetch -q origin main
  git merge -q --ff-only origin/main

  head=$(git rev-parse --short HEAD)
  [ "$head" = "$(cat deploy/.last-deployed 2>/dev/null || true)" ] && exit 0
  [ "$head" = "$(cat deploy/.last-failed 2>/dev/null || true)" ] && exit 0

  dc() { docker compose -f docker-compose.prod.yml -p kumbha-backend "$@"; }

  # The web container answers on /admin/login/ once migrations ran and gunicorn is up.
  healthy() {
    for _ in $(seq 30); do
      dc exec -T web python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/admin/login/', timeout=5)" \
        >/dev/null 2>&1 && return 0
      sleep 3
    done
    return 1
  }

  echo "==> Deploying $head: $(git log -1 --format='%s (%an)')"
  docker tag kumbha-backend kumbha-backend:previous 2>/dev/null || true
  if dc build && dc up -d --remove-orphans && healthy; then
    echo "$head" > deploy/.last-deployed
    rm -f deploy/.last-failed
    docker image prune -f >/dev/null
    echo "==> Deployed $head"
  else
    echo "$head" > deploy/.last-failed
    echo "==> Deploy FAILED for $head; rolling back to the previous image" >&2
    if docker image inspect kumbha-backend:previous >/dev/null 2>&1; then
      docker tag kumbha-backend:previous kumbha-backend
      dc up -d --remove-orphans
    fi
    exit 1
  fi
}
main "$@"
exit
