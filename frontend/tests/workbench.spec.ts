import { expect, test, type Page } from "@playwright/test"

const sampleTranscript =
  "很多人以为这只是一次普通的品牌宣传，但真正值得看的不是明星站位，而是品牌把长期行动变成公众记忆的方式。先看第一个信号，画面里没有急着喊口号，而是把人物、场景和品牌态度放在一起。第二个信号，是评论区讨论的不是单点曝光，而是这个动作是否长期一致。最后回到传播本身，最好的宣传不是突然刷屏，而是让用户感觉它早就在行动里。"

const skillOverview = {
  tasks: { processing: 0, queued: 0, completed: 0, failed: 0 },
  recent_analyses: [],
  generated_scripts: [],
  templates: [
    {
      id: "skill-controversy-hook",
      name: "争议钩子·实例升维",
      account_type: "泛娱乐观点号",
      hotspot_types: ["争议话题"],
      solves_problems: ["开头缺少清晰判断"],
      match_signals: ["公开回应", "观点分歧"],
      applicable_scenes: ["已有可核实的公开信息"],
      unsuitable_scenes: ["未经证实的爆料"],
      skeleton: ["争议钩子", "事实举例", "观点升维", "评论引导"],
      hook_formula: "先给出争议判断，再补充公开事实。",
      emotion_rhythm: "疑问 -> 理解 -> 判断",
      ending_formula: "你更认同哪种处理方式？",
      risk_boundary: "不扩写隐私，不编造内幕。",
      quality_score: 88,
      usage_count: 12,
      source_count: 1,
      source_titles: ["公开回应样本"],
      sources: [],
      status: "candidate",
      version: 1,
      owner: "内容主审",
      platforms: ["douyin"],
      required_inputs: [],
      output_contract: [],
      evaluation_summary: { passed: false },
      evidence: [
        {
          id: "evidence-controversy",
          claim: "开头应先呈现可核实的争议点。",
          source_title: "公开回应样本",
          source_url: "https://example.com/controversy",
          evidence_tier: "A",
          scope: "structure",
        },
      ],
      reviews: [],
      created_at: "2026-07-31T12:00:00.000Z",
    },
    {
      id: "skill-context-analysis",
      name: "背景拆解型",
      account_type: "商业分析号",
      hotspot_types: ["品牌危机"],
      solves_problems: ["背景信息推进不清"],
      match_signals: ["行业规律", "风险判断"],
      applicable_scenes: ["公开商业事件"],
      unsuitable_scenes: ["投资建议"],
      skeleton: ["事件一句话", "背景解释", "风险提示"],
      hook_formula: "先解释真正影响判断的背景。",
      emotion_rhythm: "理性 -> 信息增量 -> 判断",
      ending_formula: "你更关注处理速度还是处理态度？",
      risk_boundary: "不提供投资或法律结论。",
      quality_score: 84,
      usage_count: 8,
      source_count: 1,
      source_titles: ["行业案例"],
      sources: [],
      status: "candidate",
      version: 1,
      owner: "内容主审",
      platforms: ["douyin"],
      required_inputs: [],
      output_contract: [],
      evaluation_summary: { passed: false },
      evidence: [],
      reviews: [],
      created_at: "2026-07-30T12:00:00.000Z",
    },
  ],
}

async function mockSkillOverview(page: Page) {
  await page.route("**/api/v1/script-workbench/overview", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(skillOverview),
    })
  })
}

function mockedLinkTaskBody(status: "completed" | "failed") {
  const now = new Date().toISOString()
  if (status === "failed") {
    return {
      source_video: {
        id: "source_fake_link",
        input_type: "douyin_url",
        title: "抖音链接解析任务",
        url: "https://v.douyin.com/not-real-for-test/",
        status: "failed",
        material_path: null,
        created_at: now,
      },
      parser_status: "failed",
      parser_provider: "yt-dlp -> jiji262/douyin-downloader",
      output_dir: null,
      downloaded_files: [],
      video_upload: null,
      parser_error_code: "no_media",
      parser_error_title: "未识别出视频稿件",
      parser_error_detail: "测试模拟链接未产出足够视频稿件。",
      parser_action_items: ["确认分享文案里包含完整短链后重试"],
      message: "未能从抖音链接取得视频稿件；本次不生成分析。",
      fallback_inputs: [],
    }
  }

  return {
    source_video: {
      id: "source_real_link",
      input_type: "douyin_url",
      title: "抖音链接解析任务",
      url: "https://v.douyin.com/mock-real/",
      status: "completed",
      material_path: "/tmp/mock-video.mp4",
      created_at: now,
    },
    parser_status: "completed",
    parser_provider: "jiji262/douyin-downloader",
    output_dir: "/tmp/douyin-workbench",
    downloaded_files: ["/tmp/mock-video.mp4"],
    video_upload: {
      source_video: {
        id: "source_real_video",
        input_type: "video",
        title: "品牌最好的宣传其实早在行动里了",
        url: "https://v.douyin.com/mock-real/",
        author: "品牌观察室",
        status: "completed",
        material_path: "/tmp/mock-video.mp4",
        created_at: now,
      },
      audio_path: "/tmp/mock-audio.wav",
      frame_paths: [],
      extraction_status: "completed",
      asr_status: "completed",
      asr_provider: "FunASR",
      asr_text: sampleTranscript,
      ocr_status: "skipped",
      ocr_provider: "PaddleOCR",
      ocr_text: "",
      transcript: {
        id: "transcript_real_video",
        source_video_id: "source_real_video",
        asr_text: sampleTranscript,
        ocr_text: "",
        content_text: sampleTranscript,
        timestamps: [],
        confidence: 0.91,
        source: "asr",
      },
      message: "已真实提取视频稿件。",
      asr_message: "ASR 已完成。",
      ocr_message: "OCR 已跳过。",
      next_step: "拆解写作结构。",
      fallback_inputs: [],
      media_cleanup_status: "retained",
      media_cleanup_message: "测试素材。",
    },
    parser_error_code: null,
    parser_error_title: null,
    parser_error_detail: null,
    parser_action_items: [],
    message: "已真实提取视频稿件。",
    fallback_inputs: [],
  }
}

function mockedQualityReviewBody() {
  const body = mockedLinkTaskBody("completed")
  const videoUpload = body.video_upload!
  const uncertainTranscript = `${sampleTranscript} 谷爱凌摔下来，而且要开开始，还能说再来一次。`
  videoUpload.asr_text = uncertainTranscript
  videoUpload.transcript!.asr_text = uncertainTranscript
  videoUpload.transcript!.content_text = uncertainTranscript
  videoUpload.correction_status = "needs_review"
  videoUpload.corrections = [
    {
      original: "王红",
      corrected: "王虹",
      reason: "结合分享标签修正人物姓名",
      confidence: 98,
    },
  ]
  videoUpload.unresolved_fragments = [
    "谷爱凌摔下来，而且要开开始，还能说再来一次",
  ]
  videoUpload.transcript_quality_score = 72
  videoUpload.transcript_quality_message =
    "仍有 1 处无法可靠确认，已停止后续拆解。"
  videoUpload.context_terms = ["王虹", "谷爱凌"]
  return {
    ...body,
    parser_status: "failed",
    parser_error_code: "transcript_quality",
    parser_error_title: "稿件校正未通过",
    parser_error_detail: videoUpload.transcript_quality_message,
    video_upload: videoUpload,
  }
}

test("默认首页是沉淀 Skill 入口，状态条展示团队同步路径", async ({
  page,
}, testInfo) => {
  await page.goto("/")

  const brandSubtitle = page.getByText("短视频写作 Skill 工作台")
  if (testInfo.project.name === "mobile") {
    await expect(brandSubtitle).toBeHidden()
  } else {
    await expect(brandSubtitle).toBeVisible()
  }
  await expect(
    page.getByRole("heading", { name: "沉淀写作 Skill" }),
  ).toBeVisible()
  await expect(
    page.getByText("粘贴完整的抖音分享文案或短链即可开始。"),
  ).toBeVisible()

  const navigation = page.getByRole("navigation", { name: "主流程导航" })
  for (const label of ["沉淀 Skill"]) {
    await expect(
      navigation.getByRole("button", { name: label, exact: true }),
    ).toBeVisible()
  }
  await expect(
    navigation.getByRole("button", { name: "生成结构", exact: true }),
  ).toHaveCount(0)
  await expect(
    navigation.getByRole("button", { name: "填写交付", exact: true }),
  ).toHaveCount(0)
  const workflowStatus = page.getByLabel("当前流程状态")
  for (const label of ["沉淀 Skill", "团队 Skill 库", "Codex 同步"]) {
    await expect(workflowStatus.getByText(label, { exact: true })).toBeVisible()
  }
  await expect(
    page
      .getByRole("navigation", { name: "资产功能导航" })
      .getByRole("button", { name: "写作 Skill 库", exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole("button", { name: "结构分析", exact: true }),
  ).toHaveCount(0)
  await expect(
    page.getByRole("button", { name: "套路资产", exact: true }),
  ).toHaveCount(0)
  await expect(page.getByText("营销 landing page")).toHaveCount(0)
})

test.skip("结构生成过程只展示真实阶段、动作和实际耗时", async ({ page }) => {
  const now = new Date().toISOString()
  await page.route(
    "**/api/v1/script-workbench/drafts/rewrite-tasks**",
    async (route) => {
      const isCreate = route.request().method() === "POST"
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "rewrite-task-progress",
          status: isCreate ? "queued" : "processing",
          stage: isCreate ? "queued" : "fact_checking",
          stage_detail: isCreate
            ? "已进入生成队列"
            : "正在检索公开来源并交叉核验重大事实",
          progress: isCreate ? 0 : 34,
          timeout_seconds: 780,
          activities: isCreate
            ? [
                {
                  id: "activity-queued",
                  phase: "diagnosis",
                  kind: "status",
                  title: "任务已进入队列",
                  detail: "正在分配 Codex 写作任务。",
                  status: "active",
                  created_at: now,
                },
              ]
            : [
                {
                  id: "activity-old-wait",
                  phase: "research",
                  kind: "status",
                  title: "等待联网核验返回",
                  detail: "已等待 15 秒。",
                  status: "active",
                  created_at: now,
                },
                {
                  id: "activity-search",
                  phase: "research",
                  kind: "search",
                  title: "正在检索公开来源",
                  detail: "东野圭吾 讣告 出版社",
                  status: "active",
                  created_at: now,
                },
              ],
          result: null,
          error: null,
          created_at: now,
          updated_at: now,
        }),
      })
    },
  )

  await page.goto("/")
  await page
    .getByRole("textbox", { name: "你要写什么" })
    .fill("今天东野圭吾去世了，我要做一个 60 秒缅怀视频。")
  await page.getByRole("button", { name: "核实事实并生成结构" }).click()

  await expect(
    page.getByRole("heading", { name: "正在检索公开来源" }),
  ).toBeVisible()
  await expect(page.getByText("当前真实状态", { exact: true })).toBeVisible()
  await expect(
    page
      .locator(".generation-live-header")
      .getByText("东野圭吾 讣告 出版社", { exact: true }),
  ).toBeVisible()
  await expect(page.getByText("实际耗时", { exact: true })).toBeVisible()
  await expect(page.getByText("最新在最上", { exact: false })).toBeVisible()
  await expect(page.getByText("等待联网核验返回", { exact: true })).toHaveCount(
    0,
  )
  await expect(
    page.getByRole("progressbar", { name: "结构生成进度" }),
  ).toHaveCount(0)
})

test.skip("结构入口能匹配 Skill 生成结构并进入填写交付", async ({ page }) => {
  await page.goto("/")

  await page.getByLabel("输入类型").selectOption("outline")
  await page
    .getByRole("textbox", { name: "你要写什么" })
    .fill(
      "Gucci 宣传片引发时尚圈讨论，网友关注肖战和宋威龙的品牌表达。我现在只有大概方向：品牌最好的宣传其实早在行动里了，但脚本还不完整。",
    )
  await page.getByRole("button", { name: "核实事实并生成结构" }).click()

  await expect(page.getByText("事实核验")).toBeVisible({ timeout: 30000 })
  await expect(page.getByText("本次采用 Skill")).toBeVisible()
  await expect(page.getByText("本地结构工作稿", { exact: true })).toBeVisible()
  await expect(page.locator(".version-rail button")).toHaveCount(0)
  await expect(
    page.getByText("步骤 1 / 3 · 文本结构", { exact: true }),
  ).toBeVisible()
  await expect(page.locator(".studio-script-canvas")).toHaveCount(1)
  await expect(page.getByText("查看 Skill 覆盖和拍摄提示")).toBeVisible()

  await page.getByRole("button", { name: "开始填写正文" }).click()

  await expect(page.getByRole("heading", { name: "填写与交付" })).toBeVisible({
    timeout: 30000,
  })
  await expect(page.getByLabel("导出前检查")).toBeVisible()
  await expect(
    page.getByText(
      "这是本地结构工作稿，不代表 Codex 成稿。请先填写正文，再提交人工复核。",
    ),
  ).toBeVisible()
  await expect(page.getByLabel("脚本版本列表").getByRole("button")).toHaveCount(
    1,
  )
  const scriptVersionRows = page.getByLabel("脚本版本列表").getByRole("button")
  await expect(scriptVersionRows.nth(0)).toHaveAttribute("aria-pressed", "true")
  await expect(page.locator(".script-asset-row.is-active-asset")).toHaveCount(1)
  await expect(
    page.getByRole("textbox", { name: "结构稿 / 口播正文" }),
  ).toBeVisible()
  await expect(page.getByText("高级凭证配置")).toHaveCount(0)
  await expect(page.getByRole("button", { name: "执行真实门禁" })).toHaveCount(
    0,
  )
  await expect(page.getByText("API Key")).toHaveCount(0)
  await expect(page.getByText("登录态")).toHaveCount(0)

  const markdownButton = page.getByRole("button", {
    name: "Markdown",
    exact: true,
  })
  await expect(markdownButton).toBeDisabled()
  const publishableScript =
    "先把公开信息讲清楚，再从一个具体细节进入人物选择。这个动作不是单点热度，而是长期积累后的结果。"
      .repeat(5)
      .slice(0, 220)
  await page
    .getByRole("textbox", { name: "结构稿 / 口播正文" })
    .fill(publishableScript)
  await expect(page.getByText("精修中", { exact: true })).toBeVisible()
  await page.getByRole("button", { name: "提交复核" }).click()
  await expect(page.getByText("待复核", { exact: true })).toBeVisible()
  await expect(markdownButton).toBeEnabled()

  const [markdownDownload] = await Promise.all([
    page.waitForEvent("download"),
    markdownButton.click(),
  ])
  expect(markdownDownload.suggestedFilename()).toMatch(/\.md$/)

  const [jsonDownload] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "JSON", exact: true }).click(),
  ])
  expect(jsonDownload.suggestedFilename()).toMatch(/\.json$/)

  const overflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(2)
})

test.skip("填写交付支持选中文字后用 Codex 局部改写", async ({ page }) => {
  await page.route(
    "**/api/v1/script-workbench/scripts/selection-rewrite-suggestions",
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          suggestions: [
            {
              id: "work-scene",
              label: "写透作品处境",
              instruction: "选一个作品场景，写清人物处境、选择和后果。",
              reason: "当前只有作品名，没有能让观众代入的具体处境。",
              evidence_needed: true,
            },
            {
              id: "spoken-rhythm",
              label: "收紧口播节奏",
              instruction: "删掉重复判断，把长句拆成可停顿的口播短句。",
              reason: "选中段落判断重复，口播停顿不清楚。",
              evidence_needed: false,
            },
            {
              id: "connect-context",
              label: "承接上一句",
              instruction: "补一个承上启下的动作，让这段自然接住前文。",
              reason: "选区与上一句之间缺少语义连接。",
              evidence_needed: false,
            },
          ],
        }),
      })
    },
  )
  await page.route(
    "**/api/v1/script-workbench/scripts/selection-rewrite",
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          replacement:
            "《白夜行》真正留下的不是一个谜底，而是人物如何被秘密推着走向无法回头的人生。",
          change_summary: "补充作品主题，并让观点更具体。",
          supporting_facts: ["《白夜行》以案件阴影下的人物命运推进。"],
          sources: [
            {
              title: "作品介绍",
              url: "https://example.com/work",
              publisher: "出版社",
            },
          ],
        }),
      })
    },
  )

  await page.goto("/")
  await page
    .getByRole("textbox", { name: "你要写什么" })
    .fill("回顾一位推理作家的作品影响，写成一条完整口播稿。")
  await page.getByRole("button", { name: "核实事实并生成结构" }).click()
  await expect(page.getByText("本地结构工作稿", { exact: true })).toBeVisible({
    timeout: 30000,
  })
  await page.getByRole("button", { name: "开始填写正文" }).click()

  const editor = page.getByRole("textbox", { name: "结构稿 / 口播正文" })
  await editor.evaluate((element) => {
    const textarea = element as HTMLTextAreaElement
    textarea.focus()
    textarea.setSelectionRange(0, Math.min(18, textarea.value.length))
    textarea.dispatchEvent(
      new MouseEvent("mouseup", {
        bubbles: true,
        clientX: 560,
        clientY: 350,
      }),
    )
  })

  await page.getByRole("button", { name: "开始写作修改" }).click()
  await expect(page.getByRole("button", { name: /写透作品处境/ })).toBeVisible()
  await page.getByRole("button", { name: /写透作品处境/ }).click()
  await page.getByRole("button", { name: /收紧口播节奏/ }).click()
  await page
    .getByPlaceholder("还可以输入自己的修改要求")
    .fill("保留克制的缅怀语气")
  await page.getByRole("button", { name: "生成改写" }).click()

  await expect(page.getByText("补充作品主题，并让观点更具体。")).toBeVisible()
  await expect(page.getByText("本次补写依据")).toBeVisible()
  const candidate = page.getByRole("textbox", { name: "改写候选" })
  await expect(candidate).toBeEditable()
  await candidate.evaluate((element) => {
    const textarea = element as HTMLTextAreaElement
    textarea.focus()
    textarea.setSelectionRange(0, Math.min(8, textarea.value.length))
    textarea.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }))
  })
  await expect(page.getByRole("button", { name: /承接上一句/ })).toBeVisible()
  await page.getByRole("button", { name: /承接上一句/ }).click()
  const secondRewriteResponse = page.waitForResponse(
    "**/api/v1/script-workbench/scripts/selection-rewrite",
  )
  await page.getByRole("button", { name: "生成改写" }).click()
  await secondRewriteResponse
  await expect(candidate).toHaveValue(/《白夜行》真正留下的不是一个谜底/)
  const adoptButton = page.getByRole("button", { name: "采用到口播稿" })
  await expect(adoptButton).toBeEnabled()
  expect(
    await adoptButton.evaluate((element) => {
      element.scrollIntoView({ block: "center" })
      const rect = element.getBoundingClientRect()
      const hit = document.elementFromPoint(
        rect.left + rect.width / 2,
        rect.top + rect.height / 2,
      )
      return hit === element || element.contains(hit)
    }),
  ).toBe(true)
  await adoptButton.click({ force: true })
  await expect(editor).toHaveValue(/《白夜行》真正留下的不是一个谜底/)
  await expect(page.getByLabel("口播时长评估")).toContainText("预计")
})

test("Skill 列表整行可预览且不会直接跳去写稿", async ({ page }) => {
  await mockSkillOverview(page)
  const overviewResponsePromise = page.waitForResponse(
    "**/api/v1/script-workbench/overview",
  )
  await page.goto("/")
  await overviewResponsePromise
  await page
    .getByRole("navigation", { name: "资产功能导航" })
    .getByRole("button", { name: "写作 Skill 库", exact: true })
    .click()

  const rows = page.locator("[data-skill-id]")
  await expect(rows.first()).toBeVisible()
  const rowCount = await rows.count()
  expect(rowCount).toBeGreaterThan(1)
  const secondName = await rows
    .nth(1)
    .locator(".skill-row-title .table-link-button")
    .innerText()
  const secondSkill = page.getByRole("button", {
    name: `预览 Skill：${secondName}`,
    exact: true,
  })

  await secondSkill.click()

  await expect(page.locator(".template-detail-title strong")).toHaveText(
    secondName,
  )
  await expect(page.getByText("当前预览", { exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "生成文本结构" })).toHaveCount(
    0,
  )
})

test("候选 Skill 能直接进入补充来源流程", async ({ page }) => {
  await mockSkillOverview(page)
  await page.route(
    "**/api/v1/script-workbench/writing-skills/skill-controversy-hook/promotion-readiness",
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          template_id: "skill-controversy-hook",
          ready: false,
          blockers: ["还需补充来源"],
          source_count: 1,
          required_source_count: 3,
          evidence_count: 1,
          has_structure_evidence: true,
          evaluation_passed: false,
          main_review_approved: false,
        }),
      })
    },
  )
  await page.goto("/")
  await page
    .getByRole("navigation", { name: "资产功能导航" })
    .getByRole("button", { name: "写作 Skill 库", exact: true })
    .click()
  await page
    .getByRole("button", {
      name: "预览 Skill：争议钩子·实例升维",
      exact: true,
    })
    .click()
  await page.getByRole("tab", { name: "维护", exact: true }).click()

  const continueEvidence = page.getByRole("button", {
    name: "补充同类来源（还需 2 条）",
    exact: true,
  })
  await expect(continueEvidence).toBeVisible()
  await continueEvidence.click()

  await expect(page.getByRole("heading", { name: "沉淀写作 Skill" })).toBeVisible()
  await expect(page.getByText("正在补充来源", { exact: true })).toBeVisible()
  await expect(
    page.getByText("提取并保存后，本视频会自动预选为它的下一条来源。"),
  ).toBeVisible()
})

test("Skill 列表按添加时间倒序并用来源时间兜底显示日期", async ({ page }) => {
  const latestSourceDate = "2026-07-30T14:48:00.000Z"
  const olderCreatedDate = "2026-07-01T02:00:00.000Z"
  const templateBase = {
    account_type: "泛娱乐观点号",
    hotspot_types: ["反转句式写法"],
    solves_problems: ["开头缺少判断"],
    match_signals: ["结论先行", "原因后置"],
    applicable_scenes: ["已有明确结论，但缺少解释路径"],
    unsuitable_scenes: ["事实未确认的爆料"],
    skeleton: ["结论先行", "倒叙解释", "观点收束"],
    hook_formula: "先给结论，再解释为什么。",
    emotion_rhythm: "疑问 -> 理解 -> 判断",
    ending_formula: "收束成一个可回答的问题。",
    risk_boundary: "只迁移结构，不复制原句。",
    quality_score: 86,
    usage_count: 0,
    disabled_reason: null,
    last_review_note: "测试数据。",
    source_analysis_id: null,
    source_count: 1,
    pattern_fingerprint: "test-fingerprint",
  }
  await page.route("**/api/v1/script-workbench/overview", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        tasks: { processing: 0, queued: 0, completed: 2, failed: 0 },
        templates: [
          {
            ...templateBase,
            id: "older-created-skill",
            name: "旧添加日期 Skill",
            created_at: olderCreatedDate,
            source_titles: ["旧来源"],
            sources: [
              {
                source_video_id: "older-source",
                title: "旧来源",
                author: "旧账号",
                url: "https://v.douyin.com/old/",
                transcript: "旧来源文稿",
                recognized_at: olderCreatedDate,
              },
            ],
          },
          {
            ...templateBase,
            id: "latest-source-fallback-skill",
            name: "最新来源日期 Skill",
            created_at: null,
            source_titles: ["最新来源"],
            sources: [
              {
                source_video_id: "latest-source",
                title: "最新来源",
                author: "新账号",
                url: "https://v.douyin.com/latest/",
                transcript: "最新来源文稿",
                recognized_at: latestSourceDate,
              },
            ],
          },
        ],
        recent_analyses: [],
        generated_scripts: [],
      }),
    })
  })

  await page.goto("/")
  await page
    .getByRole("navigation", { name: "资产功能导航" })
    .getByRole("button", { name: "写作 Skill 库", exact: true })
    .click()

  const rows = page.locator(".skill-library-row")
  await expect(rows.first()).toContainText("最新来源日期 Skill")
  await expect(rows.first()).toContainText("添加日期 2026/07/30")
  await expect(rows.nth(1)).toContainText("旧添加日期 Skill")
  await expect(page.locator(".skill-detail-meta-row")).toContainText(
    "2026/07/30",
  )
  await expect(page.getByText("添加日期 未记录")).toHaveCount(0)
})

test("沉淀 Skill 必须基于抖音链接真实提取到的视频稿件", async ({ page }) => {
  await page.route("**/api/v1/script-workbench/link-task", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(mockedLinkTaskBody("completed")),
    })
  })
  await page.route(
    "**/api/v1/script-workbench/codex-skill-pack/publish-github",
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "published",
          repository: "example-org/douyin-writing-skills",
          url: "https://github.com/example-org/douyin-writing-skills",
          branch: "main",
          version: "test-version",
          commit_sha: "test-commit",
          message: "测试环境已模拟 GitHub 发布。",
          files_changed: 3,
        }),
      })
    },
  )

  await page.goto("/")
  await page
    .getByRole("navigation", { name: "主流程导航" })
    .getByRole("button", { name: "沉淀 Skill", exact: true })
    .click()
  await expect(
    page.getByRole("heading", { name: "沉淀写作 Skill" }),
  ).toBeVisible()
  await expect(
    page.getByRole("button", { name: "真实提取视频稿件" }),
  ).toBeDisabled()

  await page
    .getByRole("textbox", { name: "抖音分享文案或链接" })
    .fill("https://v.douyin.com/mock-real/")
  const analysisRequestPromise = page.waitForRequest(
    "**/api/v1/script-workbench/analyze-text",
  )
  const analysisResponsePromise = page.waitForResponse(
    "**/api/v1/script-workbench/analyze-text",
  )
  await page.getByRole("button", { name: "真实提取视频稿件" }).click()
  const analysisRequest = await analysisRequestPromise
  expect(analysisRequest.postDataJSON()).toMatchObject({
    source_video_id: "source_real_video",
    author: "品牌观察室",
    url: "https://v.douyin.com/mock-real/",
  })
  const analysisResponse = await analysisResponsePromise
  const analysisData = await analysisResponse.json()
  expect(analysisData.source_video).toMatchObject({
    id: "source_real_video",
    author: "品牌观察室",
    url: "https://v.douyin.com/mock-real/",
  })

  await expect(
    page.getByRole("heading", { name: "沉淀写作 Skill" }),
  ).toBeVisible({ timeout: 30000 })
  await expect(
    page.getByRole("button", { name: "确认并保存 Skill" }),
  ).toBeVisible()
  await expect(
    page.getByRole("heading", { name: "可复用写作能力" }),
  ).toBeVisible()
  await expect(page.getByText("可迁移写法", { exact: true })).toBeVisible()
  await expect(
    page.getByText("适合复用的结构条件", { exact: true }),
  ).toBeVisible()
  await expect(page.getByText("来源证据", { exact: true })).toBeVisible()
  await expect(page.getByText("视频开头", { exact: true })).toHaveCount(0)
  await page.getByRole("button", { name: "确认并保存 Skill" }).click()
  await expect(
    page.getByRole("heading", { name: "结构能力拆解" }),
  ).toBeVisible()
  await expect(
    page.getByRole("heading", { name: "确认可复用写作能力" }),
  ).toBeVisible()
  const uniqueSkillName = `测试写作 Skill ${Date.now()}`
  await page.getByRole("textbox", { name: "结构能力名" }).fill(uniqueSkillName)
  await page.route(
    "**/api/v1/script-workbench/writing-skills",
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "skill_mock_real",
          name: uniqueSkillName,
          account_type: "商业分析号",
          hotspot_types: ["反差切入", "观点升维"],
          solves_problems: ["让开头更快建立阅读理由"],
          match_signals: ["开头平", "信息散"],
          applicable_scenes: ["已有明确事实或结论，但缺少解释路径"],
          unsuitable_scenes: ["核心事实尚未确认的爆料稿"],
          skeleton: [
            "开头钩子",
            "痛点引入",
            "信息推进",
            "观点升维",
            "结尾引导",
          ],
          hook_formula: "先抛出反差或疑问，再给出一个细节入口。",
          emotion_rhythm: "好奇 -> 共鸣 -> 信息增量 -> 观点判断 -> 评论互动",
          ending_formula: "回到一个可回答的问题。",
          risk_boundary: "只学习结构，不复制原句；只基于公开信息生成。",
          quality_score: 86,
          usage_count: 0,
          disabled_reason: null,
          last_review_note: "测试环境保存。",
          source_analysis_id: "analysis_real_video",
          source_titles: ["品牌最好的宣传其实早在行动里了"],
          source_count: 1,
          pattern_fingerprint: "mock-fingerprint",
          sources: [
            {
              source_video_id: "source_real_video",
              source_analysis_id: "analysis_real_video",
              title: "品牌最好的宣传其实早在行动里了",
              author: "品牌观察室",
              url: "https://v.douyin.com/mock-real/",
              transcript: sampleTranscript,
              recognized_at: new Date().toISOString(),
            },
          ],
        }),
      })
    },
  )

  const mergeButton = page.getByRole("button", { name: "合并到已有 Skill" })
  const saveResponsePromise = page.waitForResponse(
    "**/api/v1/script-workbench/writing-skills",
  )
  if (await mergeButton.isVisible()) {
    await mergeButton.click()
  } else {
    await page.getByRole("button", { name: "保存为写作 Skill" }).click()
  }
  const saveResponse = await saveResponsePromise
  const savedSkillData = await saveResponse.json()
  expect(savedSkillData.sources).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        source_video_id: "source_real_video",
        author: "品牌观察室",
        url: "https://v.douyin.com/mock-real/",
        transcript: sampleTranscript,
      }),
    ]),
  )
  await expect(page.getByRole("heading", { name: "Skill 已保存" })).toBeVisible(
    { timeout: 30000 },
  )
  await expect(page.getByRole("button", { name: "继续沉淀视频" })).toBeVisible()
  await expect(
    page.getByRole("button", { name: "发布到 GitHub" }),
  ).toBeDisabled()
  await expect(
    page.getByText(
      "候选进度：1/3 个授权来源。正式包不会加载候选；它可继续积累证据。",
    ),
  ).toBeVisible()
  await page.getByRole("button", { name: "查看团队 Skill 库" }).click()
  await expect(
    page.getByRole("heading", { name: "写作 Skill 库" }),
  ).toBeVisible({ timeout: 30000 })
  await expect(
    page.getByRole("heading", { name: "团队 Codex Skill 包" }),
  ).toHaveCount(0)
  await expect(page.getByLabel("写作 Skill 列表")).toBeVisible()
  const savedSource = savedSkillData.sources.find(
    (source: Record<string, unknown>) =>
      source.url === "https://v.douyin.com/mock-real/",
  )
  expect(
    savedSource,
    JSON.stringify({
      saved_skill_id: savedSkillData?.id,
      saved_response_sources: savedSkillData?.sources,
    }),
  ).toBeDefined()
  expect(savedSource).toMatchObject({
    title: "品牌最好的宣传其实早在行动里了",
    author: "品牌观察室",
    url: "https://v.douyin.com/mock-real/",
    transcript: sampleTranscript,
  })
  await page.getByRole("tab", { name: "来源", exact: true }).click()
  await expect(page.getByText("来源证据")).toBeVisible()
  const savedSourceItem = page
    .locator("details.skill-source-item")
    .filter({ hasText: "品牌观察室" })
    .first()
  await expect(savedSourceItem.locator("summary")).toBeVisible()
  await savedSourceItem.locator("summary").click()
  await expect(
    savedSourceItem.getByText("原视频作者", { exact: true }),
  ).toBeVisible()
  await expect(
    savedSourceItem.getByText("品牌观察室", { exact: true }),
  ).toBeVisible()
  await expect(
    savedSourceItem.getByText("原视频链接", { exact: true }),
  ).toBeVisible()
  await expect(
    savedSourceItem.getByText("https://v.douyin.com/mock-real/", {
      exact: true,
    }),
  ).toBeVisible()
  await expect(
    savedSourceItem.getByText("原视频提取文稿", { exact: true }),
  ).toBeVisible()
  await expect(
    savedSourceItem.getByText(sampleTranscript, { exact: true }),
  ).toBeVisible()
  await expect(page.getByRole("heading", { name: "生成文本结构" })).toHaveCount(
    0,
  )
})

test("真实提取过程可感知且沉淀步骤可展开查看稿件", async ({ page }) => {
  await page.route("**/api/v1/script-workbench/link-task", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 650))
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(mockedLinkTaskBody("completed")),
    })
  })
  await page.route("**/api/v1/script-workbench/analyze-text", async (route) => {
    const response = await route.fetch()
    await new Promise((resolve) => setTimeout(resolve, 2500))
    await route.fulfill({ response })
  })

  await page.goto("/")
  await page
    .getByRole("navigation", { name: "主流程导航" })
    .getByRole("button", { name: "沉淀 Skill", exact: true })
    .click()
  await page
    .getByRole("textbox", { name: "抖音分享文案或链接" })
    .fill("https://v.douyin.com/mock-real/")
  await page.getByRole("button", { name: "真实提取视频稿件" }).click()

  await expect(page.getByRole("status")).toContainText("正在")
  await expect(page.locator(".indeterminate-progress")).toBeVisible()
  await expect(page.locator(".progress-disclosure.is-active")).toBeVisible()

  const transcriptStep = page.locator(".progress-disclosure").filter({
    hasText: "提取真实稿件",
  })
  await expect(transcriptStep).toContainText("已拿到", { timeout: 5000 })
  await transcriptStep.locator("summary").click()
  await expect(transcriptStep).toHaveAttribute("open", "")
  await expect(
    transcriptStep.getByRole("article", { name: "提取到的视频稿件" }),
  ).toBeVisible()
  expect(
    await transcriptStep.locator(".manuscript-body p").count(),
  ).toBeGreaterThan(1)
  await expect(transcriptStep.locator(".manuscript-body")).toContainText(
    "最好的宣传不是突然刷屏",
  )

  for (const title of ["识别分享链接", "拆解写作结构", "保存为 Skill"]) {
    const step = page.locator(".progress-disclosure").filter({ hasText: title })
    await step.locator("summary").click()
    await expect(step).toHaveAttribute("open", "")
  }

  await expect(
    page.getByRole("button", { name: "确认并保存 Skill" }),
  ).toBeVisible({ timeout: 30000 })
  await expect(page.getByRole("heading", { name: "结构能力拆解" })).toHaveCount(
    0,
  )
})

test("AI 无法确认的稿件会阻断，人工确认后才继续拆解", async ({ page }) => {
  await page.route("**/api/v1/script-workbench/link-task", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(mockedQualityReviewBody()),
    })
  })

  await page.goto("/")
  await page
    .getByRole("navigation", { name: "主流程导航" })
    .getByRole("button", { name: "沉淀 Skill", exact: true })
    .click()
  await page
    .getByRole("textbox", { name: "抖音分享文案或链接" })
    .fill("https://v.douyin.com/quality-review/")
  await page.getByRole("button", { name: "真实提取视频稿件" }).click()

  await expect(page.getByText("稿件校正未通过", { exact: true })).toBeVisible()
  await expect(
    page.getByRole("button", { name: "确认并保存 Skill" }),
  ).toHaveCount(0)

  const transcriptStep = page
    .locator(".progress-disclosure")
    .filter({ hasText: "提取真实稿件" })
  await transcriptStep.locator("summary").click()
  await expect(page.getByText("质量门禁未通过")).toBeVisible()
  const editor = page.getByRole("textbox", { name: "确认后的视频稿件" })
  await expect(editor).toContainText("开开始")
  await expect(editor).toHaveValue(/\n\n/)
  await editor.fill(
    `${sampleTranscript} 谷爱凌摔下来，拍拍雪站起来，还能说再来一次。`,
  )

  const analysisRequestPromise = page.waitForRequest(
    "**/api/v1/script-workbench/analyze-text",
  )
  const confirmButton = page.getByRole("button", { name: "核对完成，继续拆解" })
  await expect(confirmButton).toBeDisabled()
  await page
    .getByRole("checkbox", {
      name: "我已核对人名、数字和专业词；这份稿件可用于 Skill 分析。",
    })
    .check()
  await expect(confirmButton).toBeEnabled()
  await confirmButton.click()
  const analysisRequest = await analysisRequestPromise
  expect(analysisRequest.postDataJSON()).toMatchObject({
    content: expect.stringContaining("拍拍雪站起来"),
    transcript_source: "asr+human_review",
    transcript_confidence: 1,
  })
  await expect(
    page.getByRole("button", { name: "确认并保存 Skill" }),
  ).toBeVisible({ timeout: 30000 })
  await expect(
    page.getByText("稿件已由你人工确认，可以继续拆解。"),
  ).toBeVisible()
})

test("没有真实视频稿件时不会拆解或用标题猜内容", async ({ page }) => {
  await page.route("**/api/v1/script-workbench/link-task", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(mockedLinkTaskBody("failed")),
    })
  })
  await page.goto("/")
  await page
    .getByRole("navigation", { name: "主流程导航" })
    .getByRole("button", { name: "沉淀 Skill", exact: true })
    .click()

  await page
    .getByRole("textbox", { name: "抖音分享文案或链接" })
    .fill("https://v.douyin.com/not-real-for-test/")
  await page.getByRole("button", { name: "真实提取视频稿件" }).click()

  await expect(page.getByText("这条抖音链接暂时没有提取到视频稿件")).toBeVisible({
    timeout: 30000,
  })
  await expect(
    page.getByText("不会用标题、描述或手动文本伪装分析"),
  ).toBeVisible()
  await expect(page.getByRole("heading", { name: "结构能力拆解" })).toHaveCount(
    0,
  )
  await expect(page.getByText("上传视频")).toHaveCount(0)
  await expect(page.getByText("粘贴转写文本")).toHaveCount(0)
  await expect(page.getByText("登录态")).toHaveCount(0)
  await expect(page.getByText("downloader")).toHaveCount(0)
})

test("系统诊断从高级入口进入", async ({ page }) => {
  await page.goto("/")

  await page.getByRole("button", { name: "系统诊断" }).click()
  await expect(page.getByText("素材任务详情")).toBeVisible()
  await expect(page.getByRole("heading", { name: "系统诊断" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "首次配置" })).toBeVisible()
  await expect(page.getByRole("button", { name: "刷新门禁" })).toBeVisible()
})

test("部署环境管理模型配置时不保存空值且仍可拉取模型", async ({ page }) => {
  await page.route("**/api/v1/script-workbench/local-settings", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        llm_mode: "offline",
        llm_model: "",
        llm_api_base: "",
        skill_repository_path: "",
        skill_remote: "origin",
        skill_remote_url: "",
        skill_branch: "main",
        skill_sync_mode: "github",
        sources: {
          llm_mode: "environment",
          llm_model: "environment",
          llm_api_base: "environment",
          skill_repository_path: "default",
          skill_remote: "default",
          skill_remote_url: "default",
          skill_branch: "default",
          skill_sync_mode: "default",
        },
        llm_api_key_configured: true,
        llm_api_key_source: "environment",
        douyin_cookie_configured: false,
        douyin_cookie_source: "none",
        secret_storage: "session_only",
        secrets_persisted: false,
        publish_configured: false,
        message: "本机设置状态已读取。",
      }),
    })
  })
  await page.route("**/api/v1/script-workbench/local-settings/models", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        models: [{ id: "gpt-5.4", recommended: true, recommendation_reason: "推荐" }],
        recommended_model: "gpt-5.4",
        message: "已拉取模型列表并给出建议。",
      }),
    })
  })

  await page.goto("/")
  await page.getByRole("button", { name: "系统诊断" }).click()

  await expect(page.getByRole("combobox", { name: "模式", exact: true })).toBeDisabled()
  await expect(page.getByRole("textbox", { name: "模型", exact: true })).toHaveValue("由启动环境管理")
  await expect(page.getByRole("textbox", { name: "API Base", exact: true })).toHaveValue("由启动环境管理")
  await expect(page.getByRole("textbox", { name: "API Key", exact: true })).toHaveValue("由启动环境管理")

  const discoverModels = page.getByRole("button", { name: "拉取服务商模型" })
  await expect(discoverModels).toBeEnabled()
  await discoverModels.click()
  await expect(page.getByText("模型由启动环境固定。已拉取模型列表并给出建议。")).toBeVisible()
})
