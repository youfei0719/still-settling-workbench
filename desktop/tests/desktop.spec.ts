import { expect, test } from "@playwright/test"

const browserErrors = new Map<string, string[]>()
const transcript = "短视频写作不能只靠灵感。先核验来源与事实，再观察开头如何建立冲突，中段怎样用真实案例支撑同一判断，最后分析结尾如何收束价值。每条已授权的真实稿件都可以独立沉淀为可复用的写作 Skill。"

test.beforeEach(async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "Desktop window minimum width is 720px")
  const errors: string[] = []
  browserErrors.set(testInfo.testId, errors)
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) errors.push(message.text())
  })
  page.on("pageerror", (error) => errors.push(error.message))
  await page.goto("/")
})

test.afterEach(async ({}, testInfo) => {
  expect(browserErrors.get(testInfo.testId) ?? []).toEqual([])
  browserErrors.delete(testInfo.testId)
})

test("默认首屏体现 Skill 资产闭环", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "沉淀写作 Skill" })).toBeVisible()
  await expect(page.getByText("授权来源 → 真实稿件 → 结构沉淀 → 质量复核 → 正式版本 → 发布与加载")).toBeVisible()
  await expect(page.getByRole("heading", { name: "沉淀进度" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "可复用写作能力" })).toBeVisible()
})

test("浏览器预览不会伪造下载、转写或自动校对", async ({ page }) => {
  await page.getByLabel("抖音分享文案或短链").fill("https://v.douyin.com/example/")
  await page.getByRole("button", { name: "开始提取并转写" }).click()
  await expect(page.getByText("本次停止拆解")).toBeVisible()
  await expect(page.getByText(/真实稿件获取失败：真实下载与转写只在 Mac \/ Windows 桌面端可用/)).toBeVisible()
  await expect(page.getByText("还没有 Skill 草稿")).toBeVisible()

  await page.getByRole("button", { name: "真实稿件" }).click()
  await page.getByLabel("来源名称或链接").fill("授权来源 A")
  await page.getByLabel("经授权的真实稿件").fill(transcript)
  await page.getByText("我确认这是真实稿件且来源已获授权").click()
  await page.getByRole("button", { name: "确认真实稿件" }).click()
  await expect(page.getByText(/文本校对失败：真实模型校对只在 Mac \/ Windows 桌面端可用/)).toBeVisible()
  await expect(page.getByText("还没有 Skill 草稿")).toBeVisible()
})

test("稳定包完整性与历史质量告警分开显示", async ({ page }) => {
  await page.getByRole("button", { name: /写作 Skill 库/ }).click()
  await expect(page.getByText("5f2e84c8fa92", { exact: true })).toBeVisible()
  await expect(page.getByText("单条授权真实稿件即可沉淀一个本机 Skill")).toBeVisible()
})

test("系统诊断明确浏览器只读边界", async ({ page }) => {
  await page.getByRole("button", { name: "系统诊断" }).click()
  await expect(page.getByRole("heading", { name: "系统诊断" })).toBeVisible()
  await expect(page.getByText("浏览器开发预览")).toBeVisible()
  await expect(page.getByText(/当前是浏览器只读预览/)).toBeVisible()
  await expect(page.getByText("符合现行门禁")).toBeVisible()
  await page.getByRole("button", { name: "重新检查" }).click()
  await expect(page.getByText(/检查于/)).toBeVisible()
})

test("切换主页面时内容区回到顶部", async ({ page }) => {
  await page.getByRole("button", { name: /写作 Skill 库/ }).click()
  const main = page.locator(".skill-main > main")
  await main.evaluate((element) => { element.scrollTop = element.scrollHeight })
  expect(await main.evaluate((element) => element.scrollTop)).toBeGreaterThan(0)
  await page.getByRole("button", { name: "系统诊断" }).click()
  await expect.poll(() => main.evaluate((element) => element.scrollTop)).toBe(0)
})

test("窄桌面窗口保持主流程顺序且无根级横向溢出", async ({ page }) => {
  await page.setViewportSize({ width: 780, height: 760 })
  await expect(page.getByRole("complementary", { name: "依旧沉淀主导航" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "沉淀写作 Skill" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "沉淀进度" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "可复用写作能力" })).toBeVisible()
  const overflow = await page.locator(".skill-shell").evaluate((element) => element.scrollWidth > element.clientWidth)
  expect(overflow).toBe(false)
})
