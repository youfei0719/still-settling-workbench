#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_URL="${1:-${DOUYIN_WRITING_SKILLS_REPO_URL:-}}"

if [ -z "${REPO_URL}" ] && git -C "${SOURCE_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  REPO_URL="$(git -C "${SOURCE_DIR}" remote get-url origin)"
fi

if [ -z "${REPO_URL}" ]; then
  echo "请传入目标 Skill 仓库地址，或设置 DOUYIN_WRITING_SKILLS_REPO_URL。" >&2
  exit 1
fi

REPO_NAME="$(basename "${REPO_URL%.git}")"
TARGET_DIR="${DOUYIN_WRITING_SKILLS_TARGET_DIR:-${HOME}/.agents/skills/${REPO_NAME}}"

command -v git >/dev/null 2>&1 || { echo "需要先安装 Git。" >&2; exit 1; }
mkdir -p "${HOME}/.agents/skills"

if [ ! -e "${TARGET_DIR}" ]; then
  git clone "${REPO_URL}" "${TARGET_DIR}"
elif git -C "${TARGET_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  && [ "$(git -C "${TARGET_DIR}" remote get-url origin)" = "${REPO_URL}" ]; then
  git -C "${TARGET_DIR}" pull --ff-only origin "$(git -C "${TARGET_DIR}" branch --show-current)"
else
  echo "目标目录已存在，但 remote 与目标 Skill 仓库不一致：${TARGET_DIR}" >&2
  exit 1
fi

if command -v python3 >/dev/null 2>&1; then
  python3 "${TARGET_DIR}/scripts/load_latest.py"
else
  python "${TARGET_DIR}/scripts/load_latest.py"
fi

echo "安装完成。在 Codex 中直接使用：请用 douyin-writing-skills 写一条抖音口播。"
