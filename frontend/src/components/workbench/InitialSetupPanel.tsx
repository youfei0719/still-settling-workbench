import { Download, FolderPlus, GitBranch, KeyRound, RefreshCw, Save, ShieldCheck, Trash2 } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import {
  fetchLocalSettings,
  connectGithubRepository,
  createGithubRepository,
  createLocalRepository,
  discoverConfiguredModels,
  testConfiguredModel,
  updateLocalSettings,
  verifyLocalSettings,
} from "@/api/workbench"
import type {
  LocalSettingsStatus,
  LocalSettingsUpdatePayload,
  LocalSettingsVerification,
  ModelCatalogResponse,
} from "@/types/workbench"
import { Badge, Card, SectionHeader } from "./ui"

type Draft = {
  llm_mode: "offline" | "optional" | "required"
  llm_model: string
  llm_api_base: string
  llm_api_key: string
  douyin_cookie_string: string
  skill_repository_path: string
  skill_remote: string
  skill_remote_url: string
  skill_branch: string
  skill_sync_mode: "github" | "local"
}

function draftFromSettings(settings: LocalSettingsStatus): Draft {
  const environmentValue = (key: keyof LocalSettingsStatus["sources"], value: string) =>
    settings.sources[key] === "environment" ? "" : value
  return {
    llm_mode: (environmentValue("llm_mode", settings.llm_mode) || "offline") as Draft["llm_mode"],
    llm_model: environmentValue("llm_model", settings.llm_model),
    llm_api_base: environmentValue("llm_api_base", settings.llm_api_base),
    llm_api_key: "",
    douyin_cookie_string: "",
    skill_repository_path: environmentValue("skill_repository_path", settings.skill_repository_path),
    skill_remote: environmentValue("skill_remote", settings.skill_remote) || "origin",
    skill_remote_url: environmentValue("skill_remote_url", settings.skill_remote_url),
    skill_branch: environmentValue("skill_branch", settings.skill_branch) || "main",
    skill_sync_mode: settings.skill_sync_mode,
  }
}

export function InitialSetupPanel({
  onSettingsChanged,
}: {
  onSettingsChanged: (settings: LocalSettingsStatus) => void
}) {
  const [settings, setSettings] = useState<LocalSettingsStatus | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [verification, setVerification] =
    useState<LocalSettingsVerification | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [modelCatalog, setModelCatalog] = useState<ModelCatalogResponse | null>(null)
  const [modelTesting, setModelTesting] = useState(false)
  const [repositoryMode, setRepositoryMode] = useState<"connect" | "create" | "local">("connect")
  const [repositoryUrl, setRepositoryUrl] = useState("")
  const [repositoryName, setRepositoryName] = useState("still-settling-skills")
  const [repositoryVisibility, setRepositoryVisibility] = useState<"private" | "public">("private")
  const [repositoryParent, setRepositoryParent] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetchLocalSettings()
      setSettings(response)
      setDraft(draftFromSettings(response))
      onSettingsChanged(response)
    } catch (event) {
      setError(event instanceof Error ? event.message : "读取本机设置失败")
    } finally {
      setLoading(false)
    }
  }, [onSettingsChanged])

  useEffect(() => {
    void load()
  }, [load])

  const updateDraft = (update: Partial<Draft>) => {
    setDraft((current) => (current ? { ...current, ...update } : current))
  }

  const save = async (): Promise<boolean> => {
    if (!draft) return false
    setSaving(true)
    setError(null)
    try {
      const payload: LocalSettingsUpdatePayload = {
        llm_mode: draft.llm_mode,
        llm_model: draft.llm_model,
        llm_api_base: draft.llm_api_base,
      }
      if (draft.llm_api_key.trim()) payload.llm_api_key = draft.llm_api_key
      if (draft.douyin_cookie_string.trim()) {
        payload.douyin_cookie_string = draft.douyin_cookie_string
      }
      const response = await updateLocalSettings(payload)
      setSettings(response)
      setDraft(draftFromSettings(response))
      onSettingsChanged(response)
      setVerification(await verifyLocalSettings())
      return true
    } catch (event) {
      setError(event instanceof Error ? event.message : "保存本机设置失败")
      return false
    } finally {
      setSaving(false)
    }
  }

  const saveAndDiscoverModels = async () => {
    const saved = await save()
    if (!saved) return
    setSaving(true)
    setError(null)
    try {
      const catalog = await discoverConfiguredModels()
      setModelCatalog(catalog)
      if (catalog.recommended_model) updateDraft({ llm_model: catalog.recommended_model })
    } catch (event) {
      setError(event instanceof Error ? event.message : "拉取模型列表失败")
    } finally {
      setSaving(false)
    }
  }

  const testModel = async () => {
    setModelTesting(true)
    setError(null)
    try {
      const result = await testConfiguredModel()
      setError(result.passed ? null : result.message)
      if (result.passed) setVerification(await verifyLocalSettings())
    } catch (event) {
      setError(event instanceof Error ? event.message : "测试模型连接失败")
    } finally {
      setModelTesting(false)
    }
  }

  const applyRepositorySetup = async (
    operation: () => ReturnType<typeof connectGithubRepository>,
  ) => {
    setSaving(true)
    setError(null)
    try {
      const response = await operation()
      setSettings(response.settings)
      setDraft(draftFromSettings(response.settings))
      onSettingsChanged(response.settings)
      setVerification(await verifyLocalSettings())
    } catch (event) {
      setError(event instanceof Error ? event.message : "设置 Skill 发布项目失败")
    } finally {
      setSaving(false)
    }
  }

  const setupRepository = () => {
    const local_parent_path = repositoryParent.trim() || undefined
    if (repositoryMode === "connect") {
      void applyRepositorySetup(() => connectGithubRepository({ repository_url: repositoryUrl, local_parent_path }))
      return
    }
    if (repositoryMode === "create") {
      void applyRepositorySetup(() => createGithubRepository({ repository_name: repositoryName, visibility: repositoryVisibility, local_parent_path }))
      return
    }
    void applyRepositorySetup(() => createLocalRepository({ repository_name: repositoryName, local_parent_path }))
  }

  const verify = async () => {
    setSaving(true)
    setError(null)
    try {
      setVerification(await verifyLocalSettings())
    } catch (event) {
      setError(event instanceof Error ? event.message : "验证发布设置失败")
    } finally {
      setSaving(false)
    }
  }

  const clearSecrets = async () => {
    setSaving(true)
    setError(null)
    try {
      const response = await updateLocalSettings({
        clear_llm_key: true,
        clear_douyin_cookie: true,
      })
      setSettings(response)
      setDraft(draftFromSettings(response))
      onSettingsChanged(response)
    } catch (event) {
      setError(event instanceof Error ? event.message : "清除本机密钥失败")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className="initial-setup-panel">
      <SectionHeader
        title="首次配置"
        description="本机设置只保存在当前设备；API Key 和 Cookie 不会显示或写入项目文件。"
        action={
          <Badge tone={verification?.publish_ready ? "success" : "warning"}>
            {verification?.publish_ready ? "发布就绪" : "待配置"}
          </Badge>
        }
      />

      <div className="setup-status-row">
        <span className={settings?.llm_api_key_configured ? "status-badge status-badge-success" : "status-badge status-badge-warning"}>
          <KeyRound size={14} /> 模型密钥{settings?.llm_api_key_configured ? "已配置" : "未配置"}
        </span>
        <span className={settings?.douyin_cookie_configured ? "status-badge status-badge-success" : "status-badge status-badge-warning"}>
          <ShieldCheck size={14} /> 抖音会话{settings?.douyin_cookie_configured ? "已配置" : "使用浏览器"}
        </span>
        <span className="status-badge">
          <ShieldCheck size={14} /> {settings?.secret_storage === "system_keyring" ? "系统钥匙串" : "密钥仅本次运行"}
        </span>
      </div>

      {Object.values(settings?.sources || {}).some((source) => source === "environment") ? (
        <div className="alert-box alert-info">
          部分连接信息由启动环境管理。为避免在页面暴露，本页不显示具体值；修改前请在启动环境中更新。
        </div>
      ) : null}

      <div className="setup-section">
        <div className="setup-section-title"><KeyRound size={16} /> 模型连接</div>
        <div className="setup-grid setup-grid-model">
          <label>
            <span>模式</span>
            <select value={draft?.llm_mode || "offline"} disabled={loading} onChange={(event) => updateDraft({ llm_mode: event.target.value as Draft["llm_mode"] })}>
              <option value="offline">offline</option>
              <option value="optional">optional</option>
              <option value="required">required</option>
            </select>
          </label>
          <label>
            <span>模型</span>
            <input value={draft?.llm_model || ""} disabled={loading} onChange={(event) => updateDraft({ llm_model: event.target.value })} />
          </label>
          <label>
            <span>API Base</span>
            <input value={draft?.llm_api_base || ""} placeholder="可留空" disabled={loading} onChange={(event) => updateDraft({ llm_api_base: event.target.value })} />
          </label>
          <label>
            <span>API Key</span>
            <input value={draft?.llm_api_key || ""} type="password" placeholder="仅本机安全存储" disabled={loading} onChange={(event) => updateDraft({ llm_api_key: event.target.value })} />
          </label>
        </div>
        <div className="export-actions">
          <button type="button" className="primary-button" onClick={() => void saveAndDiscoverModels()} disabled={loading || saving}>
            <Download size={16} /> {saving ? "连接中..." : "保存并拉取模型"}
          </button>
          <button type="button" className="secondary-button" onClick={() => void testModel()} disabled={loading || saving || modelTesting}>
            <ShieldCheck size={16} /> {modelTesting ? "测试中..." : "测试连接"}
          </button>
        </div>
        {modelCatalog ? (
          <div className="setup-grid setup-grid-model">
            <label>
              <span>服务商模型</span>
              <select value={draft?.llm_model || ""} disabled={loading || saving} onChange={(event) => updateDraft({ llm_model: event.target.value })}>
                <option value="">手动填写模型名</option>
                {modelCatalog.models.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.recommended ? `推荐：${model.id}` : model.id}
                  </option>
                ))}
              </select>
            </label>
            <div className="setup-action-items">
              {modelCatalog.recommended_model
                ? `已预选推荐模型。${modelCatalog.message} 确认或更换后，点击“保存模型设置”生效。`
                : modelCatalog.message}
            </div>
          </div>
        ) : null}
      </div>

      <div className="setup-section">
        <div className="setup-section-title"><GitBranch size={16} /> Skill 发布项目</div>
        <div className="setup-grid setup-grid-repository">
          <label>
            <span>同步方式</span>
            <select value={repositoryMode} disabled={saving} onChange={(event) => setRepositoryMode(event.target.value as typeof repositoryMode)}>
              <option value="connect">连接已有 GitHub 仓库</option>
              <option value="create">创建 GitHub 仓库</option>
              <option value="local">仅本地保存</option>
            </select>
          </label>
          {repositoryMode === "connect" ? (
            <label>
              <span>GitHub 仓库地址</span>
              <input value={repositoryUrl} placeholder="https://github.com/owner/repository" disabled={saving} onChange={(event) => setRepositoryUrl(event.target.value)} />
            </label>
          ) : (
            <label>
              <span>项目名称</span>
              <input value={repositoryName} disabled={saving} onChange={(event) => setRepositoryName(event.target.value)} />
            </label>
          )}
          {repositoryMode === "create" ? (
            <label>
              <span>可见性</span>
              <select value={repositoryVisibility} disabled={saving} onChange={(event) => setRepositoryVisibility(event.target.value as "private" | "public")}>
                <option value="private">私有（推荐）</option>
                <option value="public">公开</option>
              </select>
            </label>
          ) : null}
          <label>
            <span>本地保存位置（可选）</span>
            <input value={repositoryParent} placeholder="留空则使用应用默认位置" disabled={saving} onChange={(event) => setRepositoryParent(event.target.value)} />
          </label>
        </div>
        <div className="export-actions">
          <button type="button" className="primary-button" onClick={setupRepository} disabled={saving || (repositoryMode === "connect" && !repositoryUrl.trim())}>
            <FolderPlus size={16} />
            {repositoryMode === "connect" ? "连接并自动配置" : repositoryMode === "create" ? "创建 GitHub 项目" : "创建本地项目"}
          </button>
        </div>
      </div>

      <div className="setup-section">
        <div className="setup-section-title"><ShieldCheck size={16} /> 可选抖音会话</div>
        <div className="setup-grid setup-grid-cookie">
          <label>
            <span>Cookie</span>
            <input value={draft?.douyin_cookie_string || ""} type="password" placeholder="可留空，默认读取本机浏览器" disabled={loading} onChange={(event) => updateDraft({ douyin_cookie_string: event.target.value })} />
          </label>
        </div>
      </div>

      {verification && !verification.publish_ready ? (
        <ul className="setup-action-items">
          {verification.action_items.map((item) => <li key={item}>{item}</li>)}
        </ul>
      ) : null}
      {error ? <div className="alert-box alert-warning">{error}</div> : null}
      <div className="export-actions">
        <button type="button" className="secondary-button" onClick={() => void load()} disabled={saving}>
          <RefreshCw size={16} /> 读取设置
        </button>
        <button type="button" className="primary-button" onClick={() => void save()} disabled={loading || saving}>
          <Save size={16} /> {saving ? "保存中..." : "保存模型设置"}
        </button>
        <button type="button" className="secondary-button" onClick={() => void verify()} disabled={saving}>
          <ShieldCheck size={16} /> 验证发布
        </button>
        <button type="button" className="secondary-button" onClick={() => void clearSecrets()} disabled={saving}>
          <Trash2 size={16} /> 清除密钥
        </button>
      </div>
    </Card>
  )
}
