---
name: douyin-writing-skills
description: Load the latest verified stable Douyin writing runtime from the team GitHub repository before handling requests to write, rewrite, plan, select, compare, or explain Douyin and short-video writing structures.
---

# Douyin Writing Skills Bootstrap Loader

This file is a fixed loader, not the writing workflow. The runtime `SKILL.md`
downloaded after verification is the authoritative writing Skill for this task.

Before every writing request:

1. Locate this installed Skill directory.
2. Run `python3 <skill-root>/scripts/load_latest.py`. If `python3` is unavailable, run `python <skill-root>/scripts/load_latest.py`.
3. Parse the one-line JSON response. Continue only when `status` is `ok`.
4. In the current task, read the returned `runtime_skill_path` immediately.
5. Treat that runtime `SKILL.md` as authoritative. Resolve every relative path it names from the returned `runtime_dir`, then read its `references/skills.json` and the selected writing method as required.

Do not use a cached runtime without running the loader first. Do not use writing
rules from this root directory. The loader contacts GitHub, validates the stable
manifest and every runtime file, and only then returns a runtime path.

If loading fails, stop writing and tell the user exactly:

`无法连接或验证 Douyin Writing Skills 的最新稳定版本，本次没有使用旧版本继续生成。`
