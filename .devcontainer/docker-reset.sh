#!/usr/bin/env zsh

# shellcheck disable=SC2046
docker container stop $(docker container ls -aq)
docker system prune -af
docker volume prune -af
docker network prune -f
