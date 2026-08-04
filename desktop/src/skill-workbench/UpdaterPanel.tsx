import { Download, LoaderCircle, RefreshCw } from "lucide-react"
import { UPDATER_ENDPOINT, type DesktopUpdaterState } from "./updater"

function bytes(value: number) {
  return value < 1024 * 1024 ? `${Math.round(value / 1024)} KB` : `${(value / 1024 / 1024).toFixed(1)} MB`
}

export function UpdaterPanel({ updater }: { updater: DesktopUpdaterState }) {
  if (!updater.supported) return <section className="updater-panel"><h2>自动更新</h2><p>自动更新仅在已安装的 Tauri 桌面端可用。</p></section>
  const busy = updater.status === "checking" || updater.status === "downloading" || updater.status === "installing"
  const status = updater.status === "idle" ? "等待首次检查" : updater.status === "checking" ? "正在检查" : updater.status === "available" ? "发现可用更新" : updater.status === "downloading" ? "正在下载" : updater.status === "installing" ? "正在安装并重启" : updater.status === "latest" ? "当前已是最新版本" : "更新操作失败"
  return <section className="updater-panel"><header><div><h2>桌面端更新</h2><p>当前版本：{updater.currentVersion ? `v${updater.currentVersion}` : "读取中"}</p></div><button type="button" className="secondary-command" disabled={busy} onClick={() => void updater.checkForUpdates()}>{updater.status === "checking" ? <LoaderCircle className="spin" size={14} /> : <RefreshCw size={14} />}检查更新</button></header>
    <p className="update-meta">状态：{status}<br />更新端点：<a href={UPDATER_ENDPOINT} target="_blank" rel="noreferrer">GitHub Release latest.json</a></p>
    {updater.status === "latest" ? <p className="update-status">当前已是最新版本。</p> : null}
    {updater.status === "error" ? <p className="update-status is-error">{updater.error}<a href="https://github.com/youfei0719/still-settling-workbench/releases/latest" target="_blank" rel="noreferrer">打开下载页</a></p> : null}
    {updater.update ? <div className="update-available"><strong>发现新版本 v{updater.update.version}</strong><span>当前版本 v{updater.currentVersion ?? "-"}</span>{updater.update.date ? <small>发布时间：{new Date(updater.update.date).toLocaleString("zh-CN")}</small> : null}{updater.update.notes ? <p>{updater.update.notes}</p> : null}{updater.progress ? <p>{updater.progress.stage} · {bytes(updater.progress.downloaded)}{updater.progress.total ? ` / ${bytes(updater.progress.total)}` : ""}</p> : null}<div><button type="button" className="secondary-command" disabled={busy} onClick={() => undefined}>稍后提醒</button><button type="button" className="primary-command" disabled={busy} onClick={() => void updater.installUpdate()}>{busy ? <LoaderCircle className="spin" size={14} /> : <Download size={14} />}{updater.status === "installing" ? "正在重启" : "下载并安装"}</button></div></div> : null}
    {updater.lastCheckedAt ? <small>最近检查：{new Date(updater.lastCheckedAt).toLocaleString("zh-CN")}</small> : null}
  </section>
}
