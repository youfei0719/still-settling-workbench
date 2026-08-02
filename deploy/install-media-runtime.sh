#!/usr/bin/env bash

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root on the workbench host." >&2
  exit 1
fi

APP_ROOT="${APP_ROOT:-/opt/settling-workbench}"
APP_USER="${APP_USER:-settling-workbench}"

dnf install -y ffmpeg
"${APP_ROOT}/.venv/bin/python" -m pip install --upgrade "yt-dlp[default,curl-cffi]"

install -d -o "${APP_USER}" -g "${APP_USER}" -m 0750 \
  /var/lib/settling-workbench/data/media-tasks \
  /var/lib/settling-workbench/data/media-tasks/temporary-media

echo "Media runtime installed. Configure WORKBENCH_TRANSCRIPTION_* in ${APP_ROOT}/.env before enabling link transcription."
