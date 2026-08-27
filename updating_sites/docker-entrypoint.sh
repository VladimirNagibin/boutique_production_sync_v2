#!/bin/sh
# Создаёт каталоги данных и выставляет права перед запуском приложения.
set -e

DATA_ROOT="/app/src/data"
LOG_ROOT="/app/src/logs"

mkdir -p \
  "${DATA_ROOT}/storage" \
  "${DATA_ROOT}/upload" \
  "${DATA_ROOT}/prices" \
  "${DATA_ROOT}/butic" \
  "${DATA_ROOT}/ismy" \
  "${DATA_ROOT}/ornam" \
  "${LOG_ROOT}"

if [ "$(id -u)" = "0" ]; then
  if id appuser >/dev/null 2>&1; then
    chown -R appuser:appuser "${DATA_ROOT}" "${LOG_ROOT}" || true
    exec runuser -u appuser -- "$@"
  fi
  # development / root: сделать data доступной для записи
  chmod -R a+rwX "${DATA_ROOT}" "${LOG_ROOT}" || true
fi

exec "$@"
