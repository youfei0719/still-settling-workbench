import { useCallback, useEffect, useMemo, useReducer, useRef } from "react"
import { isNativeDesktop } from "./skillWorkbenchBridge"

export const UPDATER_ENDPOINT = "https://github.com/youfei0719/still-settling-workbench/releases/latest/download/latest.json"

export type UpdaterStatus = "idle" | "checking" | "available" | "downloading" | "installing" | "latest" | "error" | "unsupported"

export type UpdateProgress = { downloaded: number; total: number | null; stage: string }

export type AvailableUpdate = {
  version: string
  date: string | null
  notes: string | null
  install: (onProgress: (progress: UpdateProgress) => void) => Promise<void>
}

type NativeUpdateInfo = Omit<AvailableUpdate, "install">

export interface UpdaterAdapter {
  supported: boolean
  getVersion: () => Promise<string | null>
  check: () => Promise<AvailableUpdate | null>
  relaunch: () => Promise<void>
}

export type DesktopUpdaterState = {
  status: UpdaterStatus
  currentVersion: string | null
  update: AvailableUpdate | null
  progress: UpdateProgress | null
  lastCheckedAt: string | null
  error: string | null
  supported: boolean
  checkForUpdates: () => Promise<void>
  installUpdate: () => Promise<void>
}

type UpdaterViewState = Omit<DesktopUpdaterState, "checkForUpdates" | "installUpdate">

export type UpdaterAction =
  | { type: "version"; value: string | null }
  | { type: "checking" }
  | { type: "available"; update: AvailableUpdate | null; checkedAt: string }
  | { type: "downloading" }
  | { type: "progress"; progress: UpdateProgress }
  | { type: "installing" }
  | { type: "error"; error: string }

export function initialUpdaterState(supported: boolean): UpdaterViewState {
  return {
    status: supported ? "idle" : "unsupported",
    currentVersion: null,
    update: null,
    progress: null,
    lastCheckedAt: null,
    error: null,
    supported,
  }
}

export function updaterReducer(state: UpdaterViewState, action: UpdaterAction): UpdaterViewState {
  switch (action.type) {
    case "version": return { ...state, currentVersion: action.value }
    case "checking": return { ...state, status: "checking", error: null }
    case "available": return { ...state, status: action.update ? "available" : "latest", update: action.update, lastCheckedAt: action.checkedAt, error: null }
    case "downloading": return { ...state, status: "downloading", progress: null, error: null }
    case "progress": return { ...state, progress: action.progress }
    case "installing": return { ...state, status: "installing" }
    case "error": return { ...state, status: "error", error: action.error }
  }
}

function message(error: unknown) {
  return error instanceof Error ? error.message : String(error)
}

export function nativeProgress(event: { event?: string; data?: { contentLength?: number; chunkLength?: number } }, progress: UpdateProgress) {
  if (event.event === "Started") return { downloaded: 0, total: event.data?.contentLength ?? null, stage: "正在下载更新包" }
  if (event.event === "Progress") return { ...progress, downloaded: progress.downloaded + (event.data?.chunkLength ?? 0), stage: "正在下载更新包" }
  if (event.event === "Finished") return { ...progress, stage: "下载完成，正在验证并安装" }
  return progress
}

export function browserUpdaterAdapter(): UpdaterAdapter {
  return {
    supported: false,
    getVersion: async () => null,
    check: async () => null,
    relaunch: async () => undefined,
  }
}

export function nativeUpdaterAdapter(): UpdaterAdapter {
  return {
    supported: true,
    async getVersion() {
      const { getVersion } = await import("@tauri-apps/api/app")
      return getVersion()
    },
    async check() {
      const { invoke } = await import("@tauri-apps/api/core")
      const update = await invoke<NativeUpdateInfo | null>("check_desktop_update")
      if (!update) return null
      return {
        version: update.version,
        date: update.date,
        notes: update.notes,
        async install(onProgress) {
          const [{ invoke }, { listen }] = await Promise.all([
            import("@tauri-apps/api/core"),
            import("@tauri-apps/api/event"),
          ])
          const unlisten = await listen<UpdateProgress>("desktop-update-progress", (event) => onProgress(event.payload))
          try {
            await invoke("install_desktop_update")
          } finally {
            unlisten()
          }
        },
      }
    },
    async relaunch() {
      const { relaunch } = await import("@tauri-apps/plugin-process")
      await relaunch()
    },
  }
}

export function defaultUpdaterAdapter() {
  return isNativeDesktop() ? nativeUpdaterAdapter() : browserUpdaterAdapter()
}

export function useDesktopUpdater(adapter = defaultUpdaterAdapter()): DesktopUpdaterState {
  const activeAdapter = useRef(adapter).current
  const [state, dispatch] = useReducer(updaterReducer, activeAdapter.supported, initialUpdaterState)
  const checking = useRef(false)

  useEffect(() => { void activeAdapter.getVersion().then((value) => dispatch({ type: "version", value })).catch(() => dispatch({ type: "version", value: null })) }, [activeAdapter])

  const checkForUpdates = useCallback(async () => {
    if (!activeAdapter.supported || checking.current) return
    checking.current = true
    dispatch({ type: "checking" })
    try {
      const next = await activeAdapter.check()
      dispatch({ type: "available", update: next, checkedAt: new Date().toISOString() })
    } catch (caught) {
      dispatch({ type: "error", error: `检查更新失败：${message(caught)}` })
    } finally {
      checking.current = false
    }
  }, [activeAdapter])

  const installUpdate = useCallback(async () => {
    if (!state.update || checking.current) return
    checking.current = true
    dispatch({ type: "downloading" })
    try {
      await state.update.install((progress) => dispatch({ type: "progress", progress }))
      dispatch({ type: "installing" })
      await activeAdapter.relaunch()
    } catch (caught) {
      dispatch({ type: "error", error: `安装更新失败：${message(caught)}` })
    } finally {
      checking.current = false
    }
  }, [activeAdapter, state.update])

  useEffect(() => {
    if (!activeAdapter.supported) return
    const timer = window.setTimeout(() => void checkForUpdates(), 1200)
    return () => window.clearTimeout(timer)
  }, [activeAdapter, checkForUpdates])

  return useMemo(() => ({ ...state, checkForUpdates, installUpdate }), [state, checkForUpdates, installUpdate])
}
