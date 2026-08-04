import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { UpdatePrompt } from "./UpdatePrompt"
import type { DesktopUpdaterState } from "./updater"

const updater: DesktopUpdaterState = {
  status: "available",
  currentVersion: "0.1.6",
  update: { version: "0.1.7", date: "2026-08-04T00:00:00Z", notes: "修复自动更新", install: async () => undefined },
  progress: null,
  lastCheckedAt: "2026-08-04T00:00:00Z",
  error: null,
  supported: true,
  checkForUpdates: async () => undefined,
  installUpdate: async () => undefined,
}

describe("更新提示", () => {
  it("displays the real current and available versions with an explicit user choice", () => {
    const markup = renderToStaticMarkup(<UpdatePrompt updater={updater} onDismiss={() => undefined} />)
    expect(markup).toContain("发现新版本 v0.1.7")
    expect(markup).toContain("当前版本 v0.1.6")
    expect(markup).toContain("稍后提醒")
    expect(markup).toContain("下载并安装")
  })
})
