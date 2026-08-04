import { describe, expect, it } from "vitest"
import { browserUpdaterAdapter, initialUpdaterState, nativeProgress, updaterReducer } from "./updater"

describe("desktop updater adapter", () => {
  it("does not pretend that browser preview can update", async () => {
    const adapter = browserUpdaterAdapter()
    expect(adapter.supported).toBe(false)
    expect(await adapter.getVersion()).toBeNull()
    expect(await adapter.check()).toBeNull()
  })

  it("tracks download progress without trusting an unknown total", () => {
    const started = nativeProgress({ event: "Started", data: { contentLength: 100 } }, { downloaded: 8, total: null, stage: "idle" })
    expect(started).toEqual({ downloaded: 0, total: 100, stage: "正在下载更新包" })
    expect(nativeProgress({ event: "Progress", data: { chunkLength: 12 } }, started)).toMatchObject({ downloaded: 12, total: 100 })
  })

  it("records latest, available, download and install states without losing the real version", () => {
    const available = { version: "0.1.7", date: null, notes: null, install: async () => undefined }
    const idle = initialUpdaterState(true)
    const latest = updaterReducer(updaterReducer(idle, { type: "checking" }), { type: "available", update: null, checkedAt: "2026-08-04T00:00:00Z" })
    expect(latest).toMatchObject({ status: "latest", update: null, lastCheckedAt: "2026-08-04T00:00:00Z" })
    const found = updaterReducer(latest, { type: "available", update: available, checkedAt: "2026-08-04T00:01:00Z" })
    expect(found).toMatchObject({ status: "available", update: available })
    const downloading = updaterReducer(found, { type: "downloading" })
    const progressed = updaterReducer(downloading, { type: "progress", progress: { downloaded: 42, total: 100, stage: "正在下载更新包" } })
    expect(progressed).toMatchObject({ status: "downloading", progress: { downloaded: 42 } })
    expect(updaterReducer(progressed, { type: "installing" }).status).toBe("installing")
  })

  it("leaves an actionable error state for both a failed check and a failed installation retry", () => {
    const failedCheck = updaterReducer(initialUpdaterState(true), { type: "error", error: "检查更新失败：network" })
    expect(failedCheck).toMatchObject({ status: "error", error: "检查更新失败：network" })
    const retry = updaterReducer(failedCheck, { type: "checking" })
    expect(retry).toMatchObject({ status: "checking", error: null })
    expect(updaterReducer(retry, { type: "error", error: "安装更新失败：signature" })).toMatchObject({ status: "error", error: "安装更新失败：signature" })
  })
})
