import { Download, LoaderCircle } from "lucide-react"
import type { DesktopUpdaterState } from "./updater"

function bytes(value: number) {
  return value < 1024 * 1024 ? `${Math.round(value / 1024)} KB` : `${(value / 1024 / 1024).toFixed(1)} MB`
}

export function UpdatePrompt({ updater, onDismiss }: { updater: DesktopUpdaterState; onDismiss: () => void }) {
  if (!updater.update) return null
  const busy = updater.status === "downloading" || updater.status === "installing"
  return <div className="update-prompt-backdrop" role="presentation"><section className="update-prompt" role="dialog" aria-modal="true" aria-labelledby="update-prompt-title"><h2 id="update-prompt-title">发现新版本 v{updater.update.version}</h2><p>当前版本 v{updater.currentVersion ?? "-"}</p>{updater.update.date ? <small>发布时间：{new Date(updater.update.date).toLocaleString("zh-CN")}</small> : null}{updater.update.notes ? <p className="update-notes">{updater.update.notes}</p> : null}{updater.progress ? <p>{updater.progress.stage} · {bytes(updater.progress.downloaded)}{updater.progress.total ? ` / ${bytes(updater.progress.total)}` : ""}</p> : null}<footer><button type="button" className="secondary-command" disabled={busy} onClick={onDismiss}>稍后提醒</button><button type="button" className="primary-command" disabled={busy} onClick={() => void updater.installUpdate()}>{busy ? <LoaderCircle className="spin" size={14} /> : <Download size={14} />}{updater.status === "installing" ? "正在重启" : "下载并安装"}</button></footer></section></div>
}
