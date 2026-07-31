#!/usr/bin/env python3
"""Reject tracked files that are unsafe for an open-source release."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PATHS = (
    re.compile(r"(^|/)\.env($|\.)"),
    re.compile(r"^frontend/\.env($|\.)"),
    re.compile(r"(^|/)\.DS_Store$"),
    re.compile(r"^undefined/"),
    re.compile(r"^evals/product-audit/"),
    re.compile(r"^evals/workbench/.*\.(?:json|md|png|jpe?g)$"),
)
ALLOWED_PATHS = {".env.example", ".env.workbench.example", "frontend/.env.example"}
# Detect user-specific home paths without embedding a previous maintainer's
# account name, machine name, or private gateway in this public checker.
ABSOLUTE_MACOS_USER_PATH = re.compile(
    r"/Users/(?!user(?:/|$)|username(?:/|$)|<[^>]+>)[^\s\"']+"
)
SECRET_ASSIGNMENT = re.compile(
    r"(?m)^(?:[A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|COOKIE)(?:$|_)[A-Z0-9_]*)\s*=\s*(?!$|\.\.\.$|<[^>]+>$|replace-with-)[^\s#].+$"
)
TOKEN_LITERAL = re.compile(r"\b(?:sk|ghp|github_pat)_[A-Za-z0-9_-]{12,}\b")


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / item.decode() for item in result.stdout.split(b"\0") if item]


def main() -> int:
    findings: list[str] = []
    for path in tracked_files():
        relative = path.relative_to(ROOT).as_posix()
        if not path.is_file():
            continue
        if relative == "scripts/verify-open-source-release.py":
            continue
        if relative not in ALLOWED_PATHS and any(
            pattern.search(relative) for pattern in FORBIDDEN_PATHS
        ):
            findings.append(f"禁止提交的路径：{relative}")
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if ABSOLUTE_MACOS_USER_PATH.search(content):
            findings.append(f"包含本机绝对用户路径：{relative}")
        if SECRET_ASSIGNMENT.search(content) or TOKEN_LITERAL.search(content):
            findings.append(f"疑似密钥或会话值：{relative}")
    if findings:
        print("开源发布检查未通过：", file=sys.stderr)
        print("\n".join(f"- {item}" for item in findings), file=sys.stderr)
        return 1
    print("开源发布检查通过：未发现受阻路径、个人标识或明文密钥。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
