#!/usr/bin/env node
import { readFileSync } from "node:fs"
import { resolve } from "node:path"

const root = resolve(import.meta.dirname, "..")
const readJson = (relative) => JSON.parse(readFileSync(resolve(root, relative), "utf8"))
const packageJson = readJson("desktop/package.json")
const tauriConfig = readJson("desktop/src-tauri/tauri.conf.json")
const cargo = readFileSync(resolve(root, "desktop/src-tauri/Cargo.toml"), "utf8")
const workflow = readFileSync(resolve(root, ".github/workflows/release-desktop.yml"), "utf8")
const cargoVersion = cargo.match(/^version\s*=\s*"([^"]+)"/m)?.[1]
const fail = (message) => { console.error(`release configuration error: ${message}`); process.exitCode = 1 }

if (!/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$/.test(packageJson.version)) fail("desktop package version is not SemVer")
if (new Set([packageJson.version, tauriConfig.version, cargoVersion]).size !== 1) fail("desktop package, Cargo and Tauri versions must match")
if (tauriConfig.bundle.createUpdaterArtifacts !== true) fail("createUpdaterArtifacts must be enabled")
const updater = tauriConfig.plugins?.updater
if (!updater?.pubkey || updater.pubkey.includes("/") || !updater.endpoints?.every((url) => url.startsWith("https://"))) fail("updater requires a public key and HTTPS endpoint")
if (!updater.endpoints.includes("https://github.com/youfei0719/still-settling-workbench/releases/latest/download/latest.json")) fail("updater endpoint is incorrect")
for (const expected of ["app-v*", "contents: write", "tauri-apps/tauri-action@v0", "uploadUpdaterJson: true", "uploadUpdaterSignatures: true", "updaterJsonPreferNsis: true", "Douyin-Writing-Skills_[version]_macOS_universal[ext]", "Douyin-Writing-Skills_[version]_windows_x64[_setup][ext]"]) if (!workflow.includes(expected)) fail(`workflow is missing ${expected}`)
if (process.exitCode) process.exit(process.exitCode)
console.log(`desktop release configuration verified for ${packageJson.version}`)
