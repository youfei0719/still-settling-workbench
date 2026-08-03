#!/usr/bin/env python3
"""Fetch the configured stable runtime and reject unverified fallback content."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote

from runtime_package import PackageValidationError, atomic_write_json, sha256_bytes, utc_now, validate_manifest, verify_package_files

LOADER_SCHEMA_VERSION = 2
USER_AGENT = "douyin-writing-skills-loader/2.0"


class LoadError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def root_dir() -> Path:
    # load_latest.py lives in <repository>/scripts/.
    return Path(__file__).resolve().parents[1]


def source_config() -> dict[str, Any]:
    try:
        value = json.loads((root_dir() / "skill-source.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LoadError("CONFIG_ERROR", "固定加载器缺少有效的 skill-source.json。") from exc
    if value.get("loader_schema_version") != LOADER_SCHEMA_VERSION:
        raise LoadError("CONFIG_ERROR", "固定加载器版本与 skill-source.json 不兼容。")
    return value


def manifest_source() -> tuple[str, str | None]:
    overridden = os.environ.get("DOUYIN_WRITING_MANIFEST_URL", "").strip()
    if overridden:
        return overridden, None
    source = source_config()
    if source.get("provider") == "local":
        repository = Path(str(source.get("repository_path", ""))).expanduser()
        return str(repository / "published/stable/manifest.json"), "local"
    owner, repository, branch = (source.get("owner"), source.get("repository"), source.get("branch"))
    if not all(isinstance(value, str) and value for value in (owner, repository, branch)):
        raise LoadError("CONFIG_ERROR", "GitHub Skill 来源配置不完整。")
    return f"https://raw.githubusercontent.com/{quote(owner)}/{quote(repository)}/{quote(branch)}/published/stable/manifest.json", "github"


def cache_dir() -> Path:
    configured = os.environ.get("DOUYIN_WRITING_CACHE_DIR", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".cache" / "douyin-writing-skills"


def timeout_seconds() -> float:
    try:
        value = float(os.environ.get("DOUYIN_WRITING_TIMEOUT", "20"))
    except ValueError as exc:
        raise LoadError("CONFIG_ERROR", "DOUYIN_WRITING_TIMEOUT 必须是数字。") from exc
    if not 0 < value <= 120:
        raise LoadError("CONFIG_ERROR", "DOUYIN_WRITING_TIMEOUT 必须在 0 到 120 秒之间。")
    return value


def fetch(source: str) -> bytes:
    path = Path(source)
    if not source.startswith(("https://", "http://")):
        try:
            return path.read_bytes()
        except OSError as exc:
            raise LoadError("NETWORK_ERROR", "无法读取本地 stable 清单或运行时文件。") from exc
    request = urllib.request.Request(source, headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache", "Pragma": "no-cache"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds()) as response:
            return response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LoadError("NETWORK_ERROR", "无法连接已配置的 Skill stable 清单或下载运行时文件。") from exc


def package_base(manifest_url: str, provider: str | None) -> str:
    if provider == "local" or not manifest_url.startswith(("https://", "http://")):
        return str(Path(manifest_url).parents[2])
    marker = "/published/stable/manifest.json"
    if marker not in manifest_url:
        raise LoadError("MANIFEST_ERROR", "清单 URL 不符合 stable 路径。")
    return manifest_url.split(marker, 1)[0]


def run() -> dict[str, str]:
    manifest_url, provider = manifest_source()
    try:
        manifest = validate_manifest(json.loads(fetch(manifest_url).decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError, PackageValidationError) as exc:
        raise LoadError("MANIFEST_ERROR", "stable manifest 无法验证。") from exc
    cache = cache_dir()
    destination = cache / "versions" / manifest["version"]
    if destination.exists():
        try:
            verify_package_files(destination, manifest)
        except PackageValidationError:
            pass
        else:
            return finish(destination, manifest, cache)
    cache.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(tempfile.mkdtemp(prefix=".download-", dir=cache))
    temporary = temporary_root / manifest["version"]
    try:
        base = package_base(manifest_url, provider)
        for item in manifest["files"]:
            target = temporary / Path(*item["path"].split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            url = str(Path(base) / manifest["package_path"] / item["path"]) if provider == "local" else f"{base}/{manifest['package_path']}/{quote(item['path'], safe='/')}"
            data = fetch(url)
            if len(data) != item["size"] or sha256_bytes(data) != item["sha256"]:
                raise LoadError("HASH_MISMATCH", f"运行时文件校验失败：{item['path']}")
            data.decode("utf-8")
            target.write_bytes(data)
        verify_package_files(temporary, manifest)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(temporary, destination)
        return finish(destination, manifest, cache)
    except UnicodeDecodeError as exc:
        raise LoadError("UTF8_ERROR", "运行时文件不是 UTF-8。") from exc
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


def finish(package: Path, manifest: dict[str, Any], cache: Path) -> dict[str, str]:
    manifest_path = package / "manifest.json"
    atomic_write_json(manifest_path, manifest)
    runtime = (package / "runtime").resolve()
    payload = {"version": manifest["version"], "runtime_dir": str(runtime), "runtime_skill_path": str(runtime / "SKILL.md"), "manifest_path": str(manifest_path.resolve()), "verified_at": utc_now()}
    atomic_write_json(cache / "current.json", payload)
    return payload


def main() -> int:
    try:
        print(json.dumps({"status": "ok", **run()}, ensure_ascii=False, separators=(",", ":")))
        return 0
    except LoadError as exc:
        print(json.dumps({"status": "error", "error_code": exc.code, "message": str(exc)}, ensure_ascii=False))
        return 1
    except Exception:
        print(json.dumps({"status": "error", "error_code": "INTERNAL_ERROR", "message": "最新稳定版本验证失败。"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
