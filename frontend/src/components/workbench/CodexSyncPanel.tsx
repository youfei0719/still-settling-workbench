import {
  CheckCircle2,
  Copy,
  ExternalLink,
  GitBranch,
  UploadCloud,
} from "lucide-react"
import { useMemo, useState } from "react"
import type {
  CodexSkillPackResponse,
  CodexSkillPublishResponse,
  LocalSettingsStatus,
} from "@/types/workbench"
import { Badge, Card, SectionHeader } from "./ui"

function copyText(value: string) {
  return navigator.clipboard?.writeText(value)
}

export function CodexSyncPanel({
  skillPack,
  publishResult,
  publishError,
  publishing,
  onPublish,
  localSettings,
}: {
  skillPack: CodexSkillPackResponse | null
  publishResult: CodexSkillPublishResponse | null
  publishError: string | null
  publishing: boolean
  onPublish: () => void
  localSettings: LocalSettingsStatus | null
}) {
  const [copied, setCopied] = useState<"install" | "update" | null>(null)
  const isGitHubSync = localSettings?.skill_sync_mode !== "local"
  const repositoryUrl = isGitHubSync
    ? publishResult?.url || localSettings?.skill_remote_url || ""
    : ""
  const repositoryName =
    publishResult?.repository ||
    repositoryUrl
      .replace(/^https:\/\/github\.com\//, "")
      .replace(/\.git$/, "") || "尚未配置"
  const installCommand = useMemo(
    () =>
      repositoryUrl
        ? `git clone ${repositoryUrl} ~/.agents/skills/douyin-writing-skills && bash ~/.agents/skills/douyin-writing-skills/scripts/install.sh`
        : "完成首次配置后生成安装命令",
    [repositoryUrl],
  )
  const updateCommand =
    "python3 ~/.agents/skills/douyin-writing-skills/scripts/load_latest.py"

  const handleCopy = (kind: "install" | "update", command: string) => {
    void copyText(command)
    setCopied(kind)
    window.setTimeout(() => setCopied(null), 1600)
  }

  return (
    <Card className="codex-sync-card">
      <SectionHeader
        title="团队 Codex 同步"
        description={
          isGitHubSync
            ? "这里处理 GitHub 发布、安装命令和同事更新状态；Skill 库只负责资产本身。"
            : "这里管理本机已发布的 Skill；需要团队共享时，可在首次配置中连接或创建 GitHub 仓库。"
        }
        action={
          <Badge tone={publishError ? "warning" : "success"}>
            {publishError ? "需要处理" : "手动发布"}
          </Badge>
        }
      />

      <div className="codex-sync-summary">
        <div>
          <span>站内同步包</span>
          <strong>{skillPack?.skill_name || "douyin-writing-skills"}</strong>
        </div>
        <div>
          <span>当前版本</span>
          <strong>
            {skillPack?.active_skill_count
              ? skillPack.version
              : "尚无可发布内容"}
          </strong>
        </div>
        <div>
          <span>启用 Skill</span>
          <strong>{skillPack?.active_skill_count ?? 0}</strong>
        </div>
        <div>
          <span>来源样本</span>
          <strong>{skillPack?.source_count ?? 0}</strong>
        </div>
      </div>

      <div className="codex-sync-publish">
        <div>
          <span className="eyebrow-text">同步目标</span>
          {localSettings?.skill_sync_mode === "local" ? (
            <strong>仅本地保存</strong>
          ) : repositoryUrl ? (
            <a href={repositoryUrl} target="_blank" rel="noreferrer">
              <GitBranch size={15} />
              {repositoryName}
              <ExternalLink size={14} />
            </a>
          ) : (
            <strong>{repositoryName}</strong>
          )}
          <p>
            {localSettings?.skill_sync_mode === "local"
              ? "发布只会写入当前设备的本地 Skill 仓库，不会连接或上传到 GitHub。"
              : "保存或复盘 Skill 后不会自动推送。确认这批 Skill 可以给同事使用时，再手动发布到 GitHub。"}
          </p>
        </div>
        <button
          type="button"
          className="primary-button"
          disabled={
            publishing ||
            !(skillPack && skillPack.active_skill_count > 0) ||
            !localSettings?.publish_configured
          }
          title={
            !localSettings?.publish_configured
              ? "请先在系统诊断完成首次配置"
              : skillPack?.active_skill_count
              ? "生成并发布新的 stable runtime"
              : "没有通过发布门槛的正式 Skill"
          }
          onClick={onPublish}
        >
          <UploadCloud size={16} />
          {publishing ? "发布中..." : localSettings?.skill_sync_mode === "local" ? "发布到本地" : "发布到 GitHub"}
        </button>
      </div>

      {publishResult ? (
        <div className="codex-sync-result" role="status">
          <CheckCircle2 size={16} />
          <span>
            {publishResult.status === "published"
              ? `已发布 ${publishResult.files_changed} 个文件`
              : isGitHubSync
                ? "GitHub 已是最新版"
                : "本地 Skill 已是最新版"}
            {publishResult.commit_sha
              ? `，提交 ${publishResult.commit_sha.slice(0, 7)}`
              : ""}
          </span>
        </div>
      ) : null}

      {publishError ? (
        <div className="alert-box alert-warning">
          <strong>{isGitHubSync ? "GitHub 发布失败" : "本地发布失败"}</strong>
          <span>{publishError}</span>
        </div>
      ) : null}

      {isGitHubSync && repositoryUrl ? <div className="codex-command-grid">
        <div className="codex-command-card">
          <span>首次安装</span>
          <code>{installCommand}</code>
          <button
            type="button"
            className="secondary-button compact-button"
            onClick={() => handleCopy("install", installCommand)}
          >
            <Copy size={14} />
            {copied === "install" ? "已复制" : "复制安装命令"}
          </button>
        </div>
        <div className="codex-command-card">
          <span>更新到最新版</span>
          <code>{updateCommand}</code>
          <button
            type="button"
            className="secondary-button compact-button"
            onClick={() => handleCopy("update", updateCommand)}
          >
            <Copy size={14} />
            {copied === "update" ? "已复制" : "复制更新命令"}
          </button>
        </div>
      </div> : null}

      <p className="codex-sync-note">
        {localSettings?.skill_sync_mode === "local"
          ? "本地模式不会生成在线安装命令；需要共享时可切换到 GitHub 同步。"
          : "连接 GitHub 仓库后，安装与更新命令会按该仓库动态生成。"}
      </p>
    </Card>
  )
}
