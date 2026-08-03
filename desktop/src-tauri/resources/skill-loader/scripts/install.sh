#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/youfei0719/douyin-writing-skills.git"
TARGET_DIR="${HOME}/.agents/skills/douyin-writing-skills"

command -v git >/dev/null 2>&1 || { echo "需要先安装 Git。" >&2; exit 1; }
mkdir -p "${HOME}/.agents/skills"

if [ ! -e "${TARGET_DIR}" ]; then
  git clone "${REPO_URL}" "${TARGET_DIR}"
elif git -C "${TARGET_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  && git -C "${TARGET_DIR}" remote get-url origin | grep -Eq 'github\.com[:/]youfei0719/douyin-writing-skills(\.git)?$'; then
  git -C "${TARGET_DIR}" pull --ff-only origin main
else
  echo "目标目录已存在，但不是 douyin-writing-skills Git 仓库：${TARGET_DIR}" >&2
  exit 1
fi

if command -v python3 >/dev/null 2>&1; then
  python3 "${TARGET_DIR}/scripts/load_latest.py"
else
  python "${TARGET_DIR}/scripts/load_latest.py"
fi

echo "安装完成。在 Codex 中直接使用：请用 douyin-writing-skills 写一条抖音口播。"
