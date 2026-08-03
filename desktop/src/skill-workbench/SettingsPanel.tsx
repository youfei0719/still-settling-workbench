import { CheckCircle2, Clipboard, FolderGit2, KeyRound, LoaderCircle, RefreshCw, ServerCog, Wrench } from "lucide-react"
import { useCallback, useEffect, useMemo, useState } from "react"
import { isNativeDesktop, skillWorkbenchBridge } from "./skillWorkbenchBridge"
import type { LocalSettings, ProviderModels, RepositorySetupRequest, SettingsUpdate } from "./types"

function message(error: unknown) {
  return error instanceof Error ? error.message : String(error)
}

export function SettingsPanel({ onSettingsChanged }: { onSettingsChanged?: () => void }) {
  const [settings, setSettings] = useState<LocalSettings | null>(null)
  const [draft, setDraft] = useState<SettingsUpdate>({})
  const [models, setModels] = useState<ProviderModels | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [setupMode, setSetupMode] = useState<RepositorySetupRequest["mode"]>("connect")
  const [repositoryUrl, setRepositoryUrl] = useState("https://github.com/youfei0719/douyin-writing-skills")
  const [repositoryName, setRepositoryName] = useState("douyin-writing-skills")
  const [visibility, setVisibility] = useState<"private" | "public">("private")
  const [parentPath, setParentPath] = useState("")

  const load = useCallback(async () => {
    setBusy("load")
    setError(null)
    try {
      const value = await skillWorkbenchBridge.getSettings()
      setSettings(value)
      if (value) {
        setDraft({
          llmMode: value.llmMode,
          llmModel: value.llmModel,
          llmApiBase: value.llmApiBase,
          asrModel: value.asrModel,
          asrApiBase: value.asrApiBase,
          skillSyncMode: value.skillSyncMode,
          skillRepositoryPath: value.skillRepositoryPath,
          skillRemote: value.skillRemote,
          skillRemoteUrl: value.skillRemoteUrl,
          skillBranch: value.skillBranch,
          networkProxy: value.networkProxy,
        })
      }
    } catch (reason) {
      setError(message(reason))
    } finally {
      setBusy(null)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const update = (patch: SettingsUpdate) => setDraft((current) => ({ ...current, ...patch }))
  const save = async () => {
    setBusy("save")
    setError(null)
    try {
      const value = await skillWorkbenchBridge.updateSettings(draft)
      setSettings(value)
      setDraft((current) => ({ ...current, llmApiKey: "", asrApiKey: "", douyinCookieString: "" }))
      const savedSecrets = [draft.llmApiKey, draft.asrApiKey, draft.douyinCookieString].some((value) => value?.trim())
      setNotice(savedSecrets ? "本机设置已保存；本次填写的密钥已进入系统凭据库。" : "本机设置已保存；本次没有新增或修改密钥。")
      onSettingsChanged?.()
      return true
    } catch (reason) {
      setError(message(reason))
      return false
    } finally {
      setBusy(null)
    }
  }

  const loadModels = async () => {
    if (!(await save())) return
    setBusy("models")
    setError(null)
    try {
      const value = await skillWorkbenchBridge.listProviderModels()
      setModels(value)
      if (value.recommendedModel) update({ llmModel: value.recommendedModel })
      setNotice(value.message)
    } catch (reason) {
      setError(message(reason))
    } finally {
      setBusy(null)
    }
  }

  const test = async () => {
    if (!(await save())) return
    setBusy("test")
    setError(null)
    try {
      const value = await skillWorkbenchBridge.testModelConnection()
      setNotice(`${value.message} · ${value.model}`)
    } catch (reason) {
      setError(message(reason))
    } finally {
      setBusy(null)
    }
  }

  const setupRepository = async () => {
    setBusy("repository")
    setError(null)
    try {
      const value = await skillWorkbenchBridge.setupRepository({
        mode: setupMode,
        repositoryUrl: setupMode === "connect" ? repositoryUrl : undefined,
        repositoryName: setupMode === "connect" ? undefined : repositoryName,
        visibility: setupMode === "create" ? visibility : undefined,
        localParentPath: parentPath || undefined,
      })
      setNotice(`${value.message}：${value.repositoryPath}`)
      await load()
      onSettingsChanged?.()
    } catch (reason) {
      setError(message(reason))
    } finally {
      setBusy(null)
    }
  }

  const commands = useMemo(() => {
    const url = settings?.skillRemoteUrl
    if (!url) return null
    const name = url.replace(/\.git$/, "").split("/").pop() || "douyin-writing-skills"
    return {
      install: `git clone ${url} ~/.agents/skills/${name} && bash ~/.agents/skills/${name}/scripts/install.sh`,
      update: `python3 ~/.agents/skills/${name}/scripts/load_latest.py`,
    }
  }, [settings?.skillRemoteUrl])

  const localAsr = draft.asrApiBase === "local://mlx-whisper"
  const chooseAsrBackend = (backend: "local" | "api") => update(backend === "local" ? {
    asrApiBase: "local://mlx-whisper",
    asrModel: "mlx-community/whisper-large-v3-turbo",
  } : {
    asrApiBase: draft.asrApiBase === "local://mlx-whisper" ? "https://api.openai.com/v1" : draft.asrApiBase,
    asrModel: (draft.asrModel ?? "").startsWith("mlx-community/") ? "whisper-1" : draft.asrModel,
  })

  if (!isNativeDesktop()) return <section className="settings-panel"><header><ServerCog size={17} /><div><h2>桌面运行时设置</h2><p>当前是浏览器只读预览。真实下载、模型、凭据和 GitHub 发布只在安装后的桌面端运行。</p></div></header></section>

  return <section className="settings-panel">
    <header><ServerCog size={17} /><div><h2>首次配置</h2><p>模型、转写和发布项目都在这里接入；密钥不写入数据库、日志或 Git 仓库。</p></div><button type="button" className="icon-command" title="刷新设置" onClick={() => void load()} disabled={busy !== null}>{busy === "load" ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />}</button></header>
    {notice ? <div className="inline-notice is-success" role="status"><CheckCircle2 size={14} />{notice}</div> : null}
    {error ? <div className="inline-notice is-danger" role="alert">{error}</div> : null}

    <div className="settings-section">
      <div className="settings-title"><KeyRound size={15} /><strong>模型与转写连接</strong><span>{settings?.llmApiKeyConfigured ? "模型密钥已保存" : "模型密钥未配置"} · {settings?.asrBackend === "local_mlx" ? "本机转写无需密钥" : settings?.asrApiKeyConfigured ? "转写密钥已保存" : "转写密钥未配置"} · 网络：{settings?.networkProxySource ?? "检查中"}</span></div>
      <div className="settings-grid">
        <label>模型模式<select value={draft.llmMode ?? "offline"} onChange={(event) => update({ llmMode: event.target.value as LocalSettings["llmMode"] })}><option value="offline">offline</option><option value="optional">optional</option><option value="required">required</option></select></label>
        <label>文本模型<input value={draft.llmModel ?? ""} onChange={(event) => update({ llmModel: event.target.value })} /></label>
        <label>文本 API Base<input value={draft.llmApiBase ?? ""} onChange={(event) => update({ llmApiBase: event.target.value })} /></label>
        <label>文本 API Key<input type="password" value={draft.llmApiKey ?? ""} placeholder={settings?.llmApiKeyConfigured ? "已安全保存；留空不修改" : "保存到系统凭据库"} onChange={(event) => update({ llmApiKey: event.target.value })} /></label>
        <div className="settings-field"><span>转写方式</span><div className="segmented compact"><button type="button" className={localAsr ? "is-active" : ""} onClick={() => chooseAsrBackend("local")}>本机 MLX</button><button type="button" className={!localAsr ? "is-active" : ""} onClick={() => chooseAsrBackend("api")}>兼容 API</button></div></div>
        <label>转写模型<input value={draft.asrModel ?? ""} onChange={(event) => update({ asrModel: event.target.value })} /></label>
        {!localAsr ? <label>转写 API Base<input value={draft.asrApiBase ?? ""} onChange={(event) => update({ asrApiBase: event.target.value })} /></label> : null}
        {!localAsr ? <label>转写 API Key<input type="password" value={draft.asrApiKey ?? ""} placeholder="留空则复用文本 API Key" onChange={(event) => update({ asrApiKey: event.target.value })} /></label> : null}
        <label>网络代理（可选）<input value={draft.networkProxy ?? ""} placeholder="留空自动使用系统/环境代理" onChange={(event) => update({ networkProxy: event.target.value })} /></label>
        <label>yt-dlp 降级 Cookie（可选）<input type="password" value={draft.douyinCookieString ?? ""} placeholder={settings?.douyinCookieConfigured ? "已安全保存；留空不修改" : "无登录浏览器解析不需要 Cookie"} onChange={(event) => update({ douyinCookieString: event.target.value })} /></label>
      </div>
      {models?.models.length ? <label className="provider-model-select">服务商模型<select value={draft.llmModel ?? ""} onChange={(event) => update({ llmModel: event.target.value })}>{models.models.map((model) => <option value={model} key={model}>{model}</option>)}</select></label> : null}
      <div className="command-row"><button type="button" className="secondary-command" onClick={() => void save()} disabled={busy !== null}>保存设置</button><button type="button" className="secondary-command" onClick={() => void loadModels()} disabled={busy !== null}>{busy === "models" ? "读取中..." : "保存并拉取模型"}</button><button type="button" className="primary-command" onClick={() => void test()} disabled={busy !== null}>{busy === "test" ? "测试中..." : "测试模型连接"}</button></div>
    </div>

    <div className="settings-section">
      <div className="settings-title"><FolderGit2 size={15} /><strong>Skill 发布项目</strong><span>{settings?.publishConfigured ? settings.skillRepositoryPath : "尚未配置"}</span></div>
      <div className="segmented compact">{([['connect', '连接 GitHub'], ['create', '创建 GitHub'], ['local', '仅本地']] as const).map(([value, label]) => <button type="button" key={value} className={setupMode === value ? "is-active" : ""} onClick={() => setSetupMode(value)}>{label}</button>)}</div>
      <div className="settings-grid repository-grid">
        {setupMode === "connect" ? <label>GitHub 仓库地址<input value={repositoryUrl} onChange={(event) => setRepositoryUrl(event.target.value)} /></label> : <label>项目名称<input value={repositoryName} onChange={(event) => setRepositoryName(event.target.value)} /></label>}
        {setupMode === "create" ? <label>可见性<select value={visibility} onChange={(event) => setVisibility(event.target.value as "private" | "public")}><option value="private">私有</option><option value="public">公开</option></select></label> : null}
        <label>本地保存父目录（可选）<input value={parentPath} placeholder="留空使用文稿目录" onChange={(event) => setParentPath(event.target.value)} /></label>
      </div>
      <button type="button" className="primary-command" onClick={() => void setupRepository()} disabled={busy !== null}><FolderGit2 size={14} />{busy === "repository" ? "配置中..." : setupMode === "connect" ? "连接并自动配置" : setupMode === "create" ? "创建并初始化" : "创建本地项目"}</button>
    </div>

    <div className="settings-section">
      <div className="settings-title"><Wrench size={15} /><strong>真实运行依赖</strong><span>桌面端检查 PATH 与系统常见安装目录，不会显示虚假健康状态</span></div>
      <div className="tool-status-grid">{settings ? [["抖音无登录解析器", settings.douyinBrowser], ["yt-dlp 降级", settings.ytDlp], ["FFmpeg", settings.ffmpeg], ["MLX Whisper", settings.mlxWhisper], ["Git", settings.git], ["GitHub CLI", settings.gh]].map(([name, status]) => { const tool = status as LocalSettings["git"]; return <div key={name as string} className={tool.available ? "is-ready" : "is-missing"} title={tool.executablePath ?? tool.version}><strong>{name as string}</strong><span>{tool.version}</span></div> }) : null}</div>
    </div>

    {commands ? <div className="settings-section codex-commands"><div className="settings-title"><Clipboard size={15} /><strong>团队 Codex 同步</strong><span>{settings?.skillRemoteUrl}</span></div>{Object.entries(commands).map(([key, command]) => <div key={key}><span>{key === "install" ? "首次安装" : "更新到 stable"}</span><code>{command}</code><button type="button" className="icon-command" title="复制命令" onClick={() => void navigator.clipboard.writeText(command)}><Clipboard size={14} /></button></div>)}</div> : null}
  </section>
}
