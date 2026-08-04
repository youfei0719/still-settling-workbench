#!/usr/bin/env node
import { execFileSync } from "node:child_process"
import { readFileSync, writeFileSync } from "node:fs"
import { homedir } from "node:os"
import { resolve } from "node:path"

const root = resolve(import.meta.dirname, "..")
const next = process.argv[2]
const semver = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/
const run = (command, args, env = process.env) => execFileSync(command, args, { cwd: root, stdio: "inherit", env })
const output = (command, args) => execFileSync(command, args, { cwd: root, encoding: "utf8" }).trim()
const localTestEnv = {
  ...process.env,
  NO_PROXY: "127.0.0.1,localhost",
  no_proxy: "127.0.0.1,localhost",
  HTTP_PROXY: "",
  HTTPS_PROXY: "",
  ALL_PROXY: "",
  http_proxy: "",
  https_proxy: "",
  all_proxy: "",
}
const compare = (left, right) => left.split(".").map(Number).reduce((result, item, index) => result || Math.sign(item - Number(right.split(".")[index])), 0)
if (!next || !semver.test(next)) throw new Error("用法：npm run release:desktop -- X.Y.Z")
if (output("git", ["branch", "--show-current"]) !== "main") throw new Error("只能从 main 发布")
if (output("git", ["status", "--porcelain"])) throw new Error("发布前工作区必须干净")
run("git", ["fetch", "origin"])
if (output("git", ["rev-parse", "HEAD"]) !== output("git", ["rev-parse", "origin/main"])) throw new Error("本地 main 必须与 origin/main 一致")
const packagePath = resolve(root, "desktop/package.json")
const packageSource = readFileSync(packagePath, "utf8")
const packageJson = JSON.parse(packageSource)
if (compare(next, packageJson.version) <= 0) throw new Error("新版本必须大于当前版本")
if (output("git", ["tag", "-l", `app-v${next}`])) throw new Error(`标签 app-v${next} 已存在`)
const tauriPath = resolve(root, "desktop/src-tauri/tauri.conf.json")
const cargoPath = resolve(root, "desktop/src-tauri/Cargo.toml")
const tauriSource = readFileSync(tauriPath, "utf8")
const cargoSource = readFileSync(cargoPath, "utf8")

try {
  packageJson.version = next
  writeFileSync(packagePath, `${JSON.stringify(packageJson, null, 2)}\n`)
  const tauri = JSON.parse(tauriSource); tauri.version = next
  writeFileSync(tauriPath, `${JSON.stringify(tauri, null, 2)}\n`)
  writeFileSync(cargoPath, cargoSource.replace(/^version\s*=\s*"[^"]+"/m, `version = "${next}"`))
  run("npm", ["ci", "--prefix", "desktop"])
  run("npm", ["run", "build", "--prefix", "desktop"])
  run("npm", ["run", "test:unit", "--prefix", "desktop"])
  run("cargo", ["test", "--manifest-path", "desktop/src-tauri/Cargo.toml", "--lib"])
  run("npm", ["run", "test", "--prefix", "desktop"], localTestEnv)
  run("npm", ["run", "acceptance:workbench"])
  run("npm", ["run", "verify:release", "--prefix", "desktop"])
  run("uv", ["run", "--project", "backend", "pytest", "backend/unit_tests"])
  run("uv", ["run", "--project", "backend", "python", "scripts/verify-open-source-release.py"])
  const signingKey = resolve(homedir(), ".tauri/douyin-writing-skills-updater.key")
  const signingPassword = output("security", ["find-generic-password", "-a", process.env.USER ?? "", "-s", "douyin-writing-skills-updater-password", "-w"])
  run("npm", ["run", "tauri:build", "--prefix", "desktop"], { ...process.env, TAURI_SIGNING_PRIVATE_KEY: readFileSync(signingKey, "utf8"), TAURI_SIGNING_PRIVATE_KEY_PASSWORD: signingPassword })
  run("git", ["diff", "--check"])
} catch (error) {
  writeFileSync(packagePath, packageSource)
  writeFileSync(tauriPath, tauriSource)
  writeFileSync(cargoPath, cargoSource)
  throw error
}
run("git", ["add", "--", "desktop/package.json", "desktop/package-lock.json", "desktop/src-tauri/Cargo.toml", "desktop/src-tauri/Cargo.lock", "desktop/src-tauri/tauri.conf.json"])
run("git", ["commit", "-m", `Release desktop v${next}`])
run("git", ["tag", "-a", `app-v${next}`, "-m", `抖音写作 Skills v${next}`])
run("git", ["push", "origin", "main"])
run("git", ["push", "origin", `app-v${next}`])
