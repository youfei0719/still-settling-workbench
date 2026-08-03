#!/usr/bin/env python3
"""Fetch and verify the latest stable runtime package; never fall back silently."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from urllib.parse import quote
from pathlib import Path
from typing import Any

from runtime_package import (
    PackageValidationError,
    atomic_write_json,
    sha256_bytes,
    utc_now,
    validate_manifest,
    verify_package_files,
)


DEFAULT_MANIFEST_URL = (
    "https://raw.githubusercontent.com/youfei0719/douyin-writing-skills/"
    "main/published/stable/manifest.json"
)
USER_AGENT = "douyin-writing-skills-loader/1.0"


class LoadError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def cache_dir() -> Path:
    configured = os.environ.get("DOUYIN_WRITING_CACHE_DIR", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".cache" / "douyin-writing-skills"


def timeout_seconds() -> float:
    value = os.environ.get("DOUYIN_WRITING_TIMEOUT", "20").strip()
    try:
        timeout = float(value)
    except ValueError as exc:
        raise LoadError("CONFIG_ERROR", "DOUYIN_WRITING_TIMEOUT 必须是数字。") from exc
    if timeout <= 0 or timeout > 120:
        raise LoadError("CONFIG_ERROR", "DOUYIN_WRITING_TIMEOUT 必须在 0 到 120 秒之间。")
    return timeout


def manifest_url() -> str:
    return os.environ.get("DOUYIN_WRITING_MANIFEST_URL", DEFAULT_MANIFEST_URL).strip()


def fetch(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache", "Pragma": "no-cache"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LoadError("NETWORK_ERROR", "无法连接 GitHub 稳定版本清单或下载运行时文件。") from exc


def fetch_manifest(url: str, timeout: float) -> dict[str, Any]:
    if not url.startswith("https://") and "DOUYIN_WRITING_MANIFEST_URL" not in os.environ:
        raise LoadError("CONFIG_ERROR", "正式稳定清单必须使用 HTTPS。")
    try:
        value = json.loads(fetch(url, timeout).decode("utf-8"))
        return validate_manifest(value)
    except UnicodeDecodeError as exc:
        raise LoadError("MANIFEST_ERROR", "稳定清单不是 UTF-8。") from exc
    except json.JSONDecodeError as exc:
        raise LoadError("MANIFEST_ERROR", "稳定清单不是有效 JSON。") from exc
    except PackageValidationError as exc:
        raise LoadError("MANIFEST_ERROR", str(exc)) from exc


def package_base_url(manifest_url_value: str, package_path: str) -> str:
    marker = "/published/stable/manifest.json"
    if marker not in manifest_url_value:
        raise LoadError("MANIFEST_ERROR", "清单 URL 不符合 GitHub Raw 稳定路径。")
    return manifest_url_value.split(marker, 1)[0] + "/" + package_path


def install_runtime(manifest: dict[str, Any], source_manifest_url: str, target_cache: Path) -> dict[str, str]:
    version = manifest["version"]
    versions = target_cache / "versions"
    destination = versions / version
    if destination.exists():
        try:
            verify_package_files(destination, manifest)
        except PackageValidationError:
            # A corrupt cache is never used; a complete, fresh download replaces it atomically.
            pass
        else:
            return current_payload(destination, manifest, target_cache)

    target_cache.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(tempfile.mkdtemp(prefix=".download-", dir=target_cache))
    temporary_package = temporary_root / version
    base_url = package_base_url(source_manifest_url, manifest["package_path"])
    try:
        for item in manifest["files"]:
            relative = Path(*item["path"].split("/"))
            output = temporary_package / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            # Manifest paths are POSIX paths but may include non-ASCII skill names.
            # Quote each complete relative path before placing it in an HTTP URL.
            encoded_path = quote(item["path"], safe="/")
            payload = fetch(f"{base_url}/{encoded_path}", timeout_seconds())
            if len(payload) != item["size"]:
                raise LoadError("SIZE_MISMATCH", f"运行时文件大小不匹配：{item['path']}")
            if sha256_bytes(payload) != item["sha256"]:
                raise LoadError("HASH_MISMATCH", f"运行时文件哈希不匹配：{item['path']}")
            try:
                payload.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise LoadError("UTF8_ERROR", f"运行时文件不是 UTF-8：{item['path']}") from exc
            output.write_bytes(payload)
        try:
            verify_package_files(temporary_package, manifest)
        except PackageValidationError as exc:
            raise LoadError("PACKAGE_ERROR", str(exc)) from exc
        versions.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            try:
                verify_package_files(destination, manifest)
            except PackageValidationError:
                shutil.rmtree(destination)
            else:
                return current_payload(destination, manifest, target_cache)
        os.replace(temporary_package, destination)
        return current_payload(destination, manifest, target_cache)
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


def current_payload(package_dir: Path, manifest: dict[str, Any], target_cache: Path) -> dict[str, str]:
    runtime_dir = (package_dir / "runtime").resolve()
    cached_manifest_path = package_dir / "manifest.json"
    atomic_write_json(cached_manifest_path, manifest)
    payload = {
        "version": manifest["version"],
        "runtime_dir": str(runtime_dir),
        "runtime_skill_path": str(runtime_dir / "SKILL.md"),
        "manifest_path": str(cached_manifest_path.resolve()),
        "verified_at": utc_now(),
    }
    atomic_write_json(target_cache / "current.json", payload)
    return payload


def run() -> dict[str, str]:
    url = manifest_url()
    manifest = fetch_manifest(url, timeout_seconds())
    return install_runtime(manifest, url, cache_dir())


def main() -> int:
    try:
        payload = {"status": "ok", **run()}
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return 0
    except LoadError as exc:
        print(json.dumps({"status": "error", "error_code": exc.code, "message": str(exc)}, ensure_ascii=False))
        return 1
    except Exception:
        print(json.dumps({"status": "error", "error_code": "INTERNAL_ERROR", "message": "最新稳定版本验证失败。"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
