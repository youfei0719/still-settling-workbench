"""Declarative runtime package validation shared by the fixed loader."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = 1
SKILL_NAME = "douyin-writing-skills"
REQUIRED_FILES = {"runtime/SKILL.md", "runtime/references/skills.json"}
ALLOWED_SUFFIXES = {".md", ".json"}
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class PackageValidationError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise PackageValidationError("文件路径必须是非空 POSIX 相对路径。")
    path = PurePosixPath(value)
    if path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise PackageValidationError("文件路径包含越界片段。")
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise PackageValidationError("运行时只允许 .md 和 .json 文件。")
    return path.as_posix()


def validate_manifest(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise PackageValidationError("manifest schema_version 不受支持。")
    if value.get("skill_name") != SKILL_NAME or value.get("channel") != "stable":
        raise PackageValidationError("manifest 不是此 Skill 的 stable 清单。")
    version = value.get("version")
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        raise PackageValidationError("manifest version 不安全。")
    if value.get("package_path") != f"published/packages/{version}" or value.get("entrypoint") != "runtime/SKILL.md":
        raise PackageValidationError("manifest 发布路径不正确。")
    try:
        datetime.fromisoformat(str(value.get("updated_at", "")).replace("Z", "+00:00"))
    except ValueError as exc:
        raise PackageValidationError("manifest updated_at 必须是 ISO 8601。") from exc
    files = value.get("files")
    if not isinstance(files, list) or not files:
        raise PackageValidationError("manifest files 缺失。")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            raise PackageValidationError("manifest 文件项无效。")
        path = validate_relative_path(item.get("path"))
        if path in seen:
            raise PackageValidationError("manifest 包含重复文件路径。")
        digest, size = item.get("sha256"), item.get("size")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise PackageValidationError("manifest 文件哈希无效。")
        if not isinstance(size, int) or size < 0:
            raise PackageValidationError("manifest 文件大小无效。")
        seen.add(path)
        normalized.append({"path": path, "sha256": digest, "size": size})
    if [entry["path"] for entry in normalized] != sorted(seen):
        raise PackageValidationError("manifest files 必须稳定排序。")
    if not REQUIRED_FILES.issubset(seen):
        raise PackageValidationError("manifest 缺少运行时入口。")
    return {**value, "version": version, "files": normalized}


def verify_package_files(package_dir: Path, manifest: object) -> None:
    checked = validate_manifest(manifest)
    actual: list[dict[str, Any]] = []
    runtime = package_dir / "runtime"
    if package_dir.is_symlink() or runtime.is_symlink() or not runtime.is_dir():
        raise PackageValidationError("运行时目录不存在或不安全。")
    for path in sorted(runtime.rglob("*")):
        if path.is_dir():
            if path.is_symlink():
                raise PackageValidationError("运行时不允许符号链接。")
            continue
        if path.is_symlink() or not path.is_file():
            raise PackageValidationError("运行时只允许普通文件。")
        data = path.read_bytes()
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PackageValidationError("运行时文件不是 UTF-8。") from exc
        actual.append({"path": validate_relative_path(path.relative_to(package_dir).as_posix()), "sha256": sha256_bytes(data), "size": len(data)})
    actual.sort(key=lambda entry: entry["path"])
    if actual != checked["files"]:
        raise PackageValidationError("运行时文件与 manifest 不一致。")


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)
