import { Play, RotateCcw, Square } from "lucide-react"
import type {
  LinkTaskResponse,
  ModelRuntimeStatus,
  VideoExtractionTask,
  VideoUploadResponse,
} from "@/types/workbench"
import {
  extractorStatusLabel,
  formatTaskTime,
  videoTaskStatusLabel,
  videoTaskStatusToBadgeStatus,
} from "./statusLabels"
import { Card, EmptyState, SectionHeader, StatusBadge } from "./ui"

export function MaterialTaskPanel({
  title,
  linkTask,
  videoUpload,
  videoExtractionTask,
  videoExtractionTasks,
  runAsr,
  runOcr,
  modelStatus,
  extractionLoading,
  warmupLoading,
  uploadNotice,
  onRunAsrChange,
  onRunOcrChange,
  onWarmupCheck,
  onWarmupExecute,
  onStartVideoExtraction,
  onCancelVideoExtraction,
  onRetryVideoExtraction,
}: {
  title: string
  linkTask: LinkTaskResponse | null
  videoUpload: VideoUploadResponse | null
  videoExtractionTask: VideoExtractionTask | null
  videoExtractionTasks: VideoExtractionTask[]
  runAsr: boolean
  runOcr: boolean
  modelStatus: ModelRuntimeStatus | null
  extractionLoading: boolean
  warmupLoading: boolean
  uploadNotice: string | null
  onRunAsrChange: (value: boolean) => void
  onRunOcrChange: (value: boolean) => void
  onWarmupCheck: () => void
  onWarmupExecute: () => void
  onStartVideoExtraction: () => void
  onCancelVideoExtraction: () => void
  onRetryVideoExtraction: () => void
}) {
  const materialTitle =
    videoUpload?.source_video.title || linkTask?.source_video.title || title
  const materialPath =
    videoUpload?.source_video.material_path ||
    linkTask?.source_video.material_path
  const hasMaterial = Boolean(videoUpload || linkTask)
  const asrModel = modelStatus?.items.find((item) => item.key === "asr")
  const ocrModel = modelStatus?.items.find((item) => item.key === "ocr")

  return (
    <Card className="material-task-sidebar">
      <SectionHeader
        title="2. 素材任务详情"
        description="把链接诊断、模型状态和后台任务集中在这里处理。"
      />
      <aside className="material-detail-stack" aria-label="素材任务详情">
        {uploadNotice ? (
          <div className="alert-box alert-success">
            <strong>当前素材状态</strong>
            <span>{uploadNotice}</span>
          </div>
        ) : null}

        {videoUpload?.media_cleanup_status === "completed" ? (
          <div className="alert-box alert-success">
            <strong>临时素材已清理</strong>
            <span>{videoUpload.media_cleanup_message}</span>
          </div>
        ) : videoUpload?.media_cleanup_status === "failed" ? (
          <div className="alert-box alert-warning">
            <strong>临时素材待清理</strong>
            <span>{videoUpload.media_cleanup_message}</span>
          </div>
        ) : null}

        {linkTask?.parser_error_title ? (
          <div
            className={`parser-diagnostic parser-diagnostic-${linkTask.parser_error_code || "unknown"}`}
          >
            <strong>{linkTask.parser_error_title || "链接解析未完成"}</strong>
            <span>
              {linkTask.parser_error_detail ||
                "当前链接暂未取得可分析素材，请确认完整分享文案后重试。"}
            </span>
            {linkTask.parser_action_items.length > 0 ? (
              <ul>
                {linkTask.parser_action_items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        <div className="material-facts">
          <div>
            <span>素材</span>
            <strong>{hasMaterial ? materialTitle : "尚未进入素材池"}</strong>
          </div>
          <div>
            <span>视频文件</span>
            <strong>{materialPath || "等待链接提取"}</strong>
          </div>
          <div>
            <span>音频</span>
            <strong>
              {videoUpload?.audio_path ||
                videoExtractionTask?.audio_path ||
                "未抽取"}
            </strong>
          </div>
          <div>
            <span>关键帧</span>
            <strong>
              {videoUpload?.frame_paths.length ||
                videoExtractionTask?.frame_paths.length ||
                0}{" "}
              张
            </strong>
          </div>
        </div>

        <div className="model-runtime-panel">
          <div className="model-option-grid">
            <label className="model-option">
              <input
                type="checkbox"
                checked={runAsr}
                onChange={(event) => onRunAsrChange(event.target.checked)}
              />
              <span>
                <strong>ASR 口播转写</strong>
                <small>{asrModel?.detail || "未执行模型检查"}</small>
              </span>
            </label>
            <label className="model-option">
              <input
                type="checkbox"
                checked={runOcr}
                onChange={(event) => onRunOcrChange(event.target.checked)}
              />
              <span>
                <strong>OCR 硬字幕识别</strong>
                <small>{ocrModel?.detail || "未执行模型检查"}</small>
              </span>
            </label>
          </div>
          <div className="model-runtime-actions">
            <span>
              {modelStatus?.message ||
                "先做预热检查可确认本机是否已经具备 ASR/OCR 运行条件。"}
            </span>
            <button
              type="button"
              className="secondary-button compact-button"
              onClick={onWarmupCheck}
              disabled={warmupLoading}
            >
              预热检查
            </button>
            <button
              type="button"
              className="secondary-button compact-button"
              onClick={onWarmupExecute}
              disabled={warmupLoading}
            >
              执行预热
            </button>
          </div>
        </div>

        {videoExtractionTask ? (
          <div className="extract-task-panel">
            <div className="extract-task-head">
              <div>
                <strong>后台提取任务</strong>
                <span>
                  {videoExtractionTask.stage_detail ||
                    videoExtractionTask.next_step}
                </span>
              </div>
              <StatusBadge
                status={videoTaskStatusToBadgeStatus(
                  videoExtractionTask.status,
                )}
              />
            </div>
            <div className="progress-track" aria-label="后台提取进度">
              <span
                style={{
                  width: `${Math.max(0, Math.min(100, videoExtractionTask.progress))}%`,
                }}
              />
            </div>
            <div className="task-stage-grid">
              <span>阶段：{videoExtractionTask.stage}</span>
              <span>
                ASR：{extractorStatusLabel(videoExtractionTask.asr_status)} /
                OCR：{extractorStatusLabel(videoExtractionTask.ocr_status)}
              </span>
              <span>
                更新时间：{formatTaskTime(videoExtractionTask.updated_at)}
              </span>
            </div>
            {videoExtractionTask.error ? (
              <small className="error-text">{videoExtractionTask.error}</small>
            ) : null}
            <div className="extract-task-actions">
              {videoExtractionTask.status === "queued" ||
              videoExtractionTask.status === "processing" ? (
                <button
                  type="button"
                  className="secondary-button compact-button"
                  onClick={onCancelVideoExtraction}
                >
                  <Square size={14} />
                  取消
                </button>
              ) : null}
              {videoExtractionTask.status === "failed" ||
              videoExtractionTask.status === "cancelled" ? (
                <button
                  type="button"
                  className="secondary-button compact-button"
                  onClick={onRetryVideoExtraction}
                  disabled={extractionLoading}
                >
                  <RotateCcw size={14} />
                  重试
                </button>
              ) : null}
            </div>
          </div>
        ) : videoUpload ? (
          <div className="extract-task-panel">
            <div className="extract-task-head">
              <div>
                <strong>后台提取未启动</strong>
                <span>
                  视频已经保存，可以按需启动
                  ASR/OCR；也可以直接上传字幕或粘贴文本继续。
                </span>
              </div>
              <StatusBadge status="pending" />
            </div>
            <button
              type="button"
              className="secondary-button compact-button"
              onClick={onStartVideoExtraction}
              disabled={extractionLoading}
            >
              <Play size={14} />
              启动后台提取
            </button>
          </div>
        ) : (
          <EmptyState
            title="暂无素材任务"
            description="提交抖音分享链接后，这里会显示提取进度、路径和模型状态。"
          />
        )}

        <div className="task-history-list">
          <div className="task-history-title">
            <strong>最近任务</strong>
            <span>{videoExtractionTasks.length} 条</span>
          </div>
          {videoExtractionTasks.length > 0 ? (
            videoExtractionTasks.map((task) => (
              <div key={task.id} className="task-history-item">
                <div>
                  <strong>{task.source_video.title}</strong>
                  <span>{task.stage_detail || task.next_step}</span>
                </div>
                <div>
                  <StatusBadge
                    status={videoTaskStatusToBadgeStatus(task.status)}
                  />
                  <small>
                    {videoTaskStatusLabel(task.status)} ·{" "}
                    {formatTaskTime(task.updated_at)}
                  </small>
                </div>
              </div>
            ))
          ) : (
            <span className="helper-line">还没有后台提取历史。</span>
          )}
        </div>
      </aside>
    </Card>
  )
}
