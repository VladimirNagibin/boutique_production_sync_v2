#!/bin/sh
# Создаёт каталоги загрузок и выставляет права перед запуском приложения.
set -e

DATA_ROOT="/app/src/data"
LOG_ROOT="/app/src/logs"

mkdir -p \
  "${DATA_ROOT}/upload/in" \
  "${DATA_ROOT}/upload/out" \
  "${LOG_ROOT}"

if [ "$(id -u)" = "0" ]; then
  if id appuser >/dev/null 2>&1; then
    chown -R appuser:appuser "${DATA_ROOT}" "${LOG_ROOT}" || true
    exec runuser -u appuser -- "$@"
  fi
  chmod -R a+rwX "${DATA_ROOT}" "${LOG_ROOT}" || true
fi

exec "$@"
