import {
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  Circle,
  CircleDot,
  Link2,
  LoaderCircle,
  ShieldAlert,
} from "lucide-react";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import type {
  AnalyzeTextResponse,
  LinkTaskResponse,
  ServerMediaTask,
  TemplatePattern,
  VideoUploadResponse,
} from "@/types/workbench";
import { Badge, Card, EmptyState, SectionHeader } from "./ui";

type ProgressState = "waiting" | "active" | "complete" | "ready" | "failed";

function manuscriptParagraphs(content: string) {
  const normalized = content
    .replace(/\r/g, "")
    .replace(/[A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*){2,}/g, " ")
    .replace(/[ \t]+/g, " ")
    .trim();
  if (!normalized) return [];

  const explicitParagraphs = normalized
    .split(/\n\s*\n+/)
    .map((paragraph) => paragraph.replace(/\s*\n\s*/g, "").trim())
    .filter(Boolean);

  if (explicitParagraphs.length > 1) return explicitParagraphs;

  const sentences = normalized
    .replace(/\s*\n\s*/g, "")
    .match(/[^。！？!?；;]+[。！？!?；;]?/g)
    ?.map((sentence) => sentence.trim())
    .filter(Boolean) || [normalized];

  const paragraphs: string[] = [];
  let current = "";
  for (const sentence of sentences) {
    if (current && current.length + sentence.length > 90) {
      paragraphs.push(current);
      current = sentence;
    } else {
      current += sentence;
    }
  }
  if (current) paragraphs.push(current);
  return paragraphs;
}

function editableManuscript(content: string) {
  return manuscriptParagraphs(content).join("\n\n");
}

function preferredTranscript(videoUpload: VideoUploadResponse | null) {
  const contentText = videoUpload?.transcript?.content_text?.trim() || "";
  const asrText = videoUpload?.asr_text?.trim() || "";
  if (asrText.length >= 10 && contentText.length > asrText.length * 1.25) {
    return asrText;
  }
  return (
    contentText || [asrText, videoUpload?.ocr_text].filter(Boolean).join("\n")
  );
}

function ProgressDisclosure({
  title,
  summary,
  state,
  children,
}: {
  title: string;
  summary: string;
  state: ProgressState;
  children: ReactNode;
}) {
  const StateIcon =
    state === "complete"
      ? CheckCircle2
      : state === "active"
        ? LoaderCircle
        : state === "ready"
          ? CircleDot
          : state === "failed"
            ? ShieldAlert
            : Circle;
  const stateLabel =
    state === "complete"
      ? "已完成"
      : state === "active"
        ? "处理中"
        : state === "ready"
          ? "待确认"
          : state === "failed"
            ? "未完成"
            : "等待中";

  return (
    <details className={`progress-disclosure is-${state}`}>
      <summary>
        <span className="progress-state-icon" aria-hidden="true">
          <StateIcon size={17} />
        </span>
        <span className="progress-step-copy">
          <strong>{title}</strong>
          <span>{summary}</span>
        </span>
        <span className="progress-step-status">{stateLabel}</span>
        <ChevronDown
          className="progress-chevron"
          size={17}
          aria-hidden="true"
        />
      </summary>
      <div className="progress-step-detail">{children}</div>
    </details>
  );
}

export function LinkConsole({
  url,
  loading,
  error,
  serverMediaTask,
  linkTask,
  videoUpload,
  analysis,
  onUrlChange,
  onAnalyzeLink,
  onConfirmTranscript,
  onViewAnalysis,
  evidenceTarget,
}: {
  url: string;
  loading: boolean;
  error: string | null;
  serverMediaTask: ServerMediaTask | null;
  linkTask: LinkTaskResponse | null;
  videoUpload: VideoUploadResponse | null;
  analysis: AnalyzeTextResponse | null;
  onUrlChange: (value: string) => void;
  onAnalyzeLink: () => void;
  onConfirmTranscript: (content: string) => void;
  onViewAnalysis: () => void;
  evidenceTarget: TemplatePattern | null;
}) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [reviewText, setReviewText] = useState("");
  const [reviewConfirmed, setReviewConfirmed] = useState(false);

  useEffect(() => {
    if (!loading) {
      setElapsedSeconds(0);
      return;
    }
    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      setElapsedSeconds(
        Math.max(1, Math.floor((Date.now() - startedAt) / 1000)),
      );
    }, 1000);
    return () => window.clearInterval(timer);
  }, [loading]);

  const transcriptText = preferredTranscript(videoUpload);
  const hasTranscript = transcriptText.trim().length >= 10;
  const hasFailed = Boolean(linkTask && linkTask.parser_status !== "completed");
  const qualityNeedsReview =
    linkTask?.parser_error_code === "transcript_quality" ||
    videoUpload?.correction_status === "needs_review";
  const extractionFailed = hasFailed && !qualityNeedsReview;
  const canSubmit = url.trim().length >= 8 && !loading;
  const transcriptParagraphs = useMemo(
    () => manuscriptParagraphs(transcriptText),
    [transcriptText],
  );
  const sourceVideo = videoUpload?.source_video || linkTask?.source_video;
  const isExtracting = loading && !linkTask;
  const isAnalyzing = loading && hasTranscript && !analysis;
  const loadingMessage = isAnalyzing
    ? "正在拆解稿件的开头、推进、情绪和结尾"
    : serverMediaTask?.stage || serverMediaTask?.stage_detail
      ? serverMediaTask.stage || serverMediaTask.stage_detail
      : elapsedSeconds >= 12
        ? "正在服务器下载视频并识别语音，长视频需要多一点时间"
        : elapsedSeconds >= 4
          ? "正在从公开视频提取真实稿件"
          : "正在将链接交给主站媒体任务";

  useEffect(() => {
    if (qualityNeedsReview && transcriptText) {
      setReviewText(editableManuscript(transcriptText));
      setReviewConfirmed(false);
    }
  }, [qualityNeedsReview, transcriptText]);

  return (
    <div className="page-grid page-grid-workbench">
      <Card className="input-panel">
        <SectionHeader
          title="沉淀写作 Skill"
          description="粘贴完整的抖音分享文案或短链即可开始。主站会免登录临时处理媒体，只保留真实文稿、分析历史和 Skill。"
        />

        {evidenceTarget ? (
          <div className="next-step-callout" role="status">
            <div>
              <span>正在补充来源</span>
              <strong>
                「{evidenceTarget.name}」当前 {evidenceTarget.source_count || 0}
                /3
              </strong>
            </div>
            <span>提取并保存后，本视频会自动预选为它的下一条来源。</span>
          </div>
        ) : null}

        <label className="field-label" htmlFor="douyin-url">
          抖音分享文案或链接
        </label>
        <div className="input-action-row">
          <input
            id="douyin-url"
            className="text-input"
            value={url}
            onChange={(event) => onUrlChange(event.target.value)}
            placeholder="粘贴抖音复制出来的一整段分享文案或短链"
          />
          <button
            type="button"
            className="primary-button"
            onClick={onAnalyzeLink}
            disabled={!canSubmit}
          >
            {loading ? (
              <LoaderCircle className="button-spinner" size={16} />
            ) : (
              <Link2 size={16} />
            )}
            {loading ? "主站媒体处理中..." : "开始提取并转写"}
          </button>
        </div>

        {loading ? (
          <div className="extraction-loading" role="status" aria-live="polite">
            <div className="extraction-loading-head">
              <span>
                <LoaderCircle
                  className="button-spinner"
                  size={18}
                  aria-hidden="true"
                />
                <strong>{loadingMessage}</strong>
              </span>
              <small>{elapsedSeconds} 秒</small>
            </div>
            <div className="indeterminate-progress" aria-hidden="true">
              <span />
            </div>
            <p>页面可以保持打开，完成后会在当前页显示校正稿和拆解结果。</p>
          </div>
        ) : null}

        {error ? (
          <div className="alert-box alert-error">
            <strong>
              {qualityNeedsReview ? "稿件校正未通过" : "主站媒体任务未完成"}
            </strong>
            <span>{error}</span>
          </div>
        ) : null}

        {hasFailed ? (
          <div className="next-step-callout next-step-error">
            <ShieldAlert size={18} />
            <div>
              <strong>
                {qualityNeedsReview
                  ? "稿件有疑点，本次停止拆解"
                  : "本次停止拆解"}
              </strong>
              <span>
                {qualityNeedsReview
                  ? "系统保留了 AI 转写稿和待确认片段，但不会让它进入写法分析或 Skill。"
                  : "系统不会用标题、描述或手动文本伪装分析。请确认粘贴的是完整分享文案或短链，然后重试。"}
              </span>
            </div>
          </div>
        ) : hasTranscript ? (
          <div className="next-step-callout">
            <CheckCircle2 size={18} />
            <div>
              <strong>
                {analysis ? "视频稿件和写法拆解已完成" : "已真实提取视频稿件"}
              </strong>
              <span>
                {analysis
                  ? "真实稿件和结构 Skill 草稿已经就绪。确认后保存，这次沉淀任务就完成。"
                  : "正在基于真实稿件拆解文本结构，并生成可确认的 Skill 草稿。"}
              </span>
            </div>
          </div>
        ) : (
          <div className="helper-line">
            这个功能只做 Skill 资产沉淀：提不到真实视频稿件，就不会继续拆解。
          </div>
        )}
      </Card>

      <Card>
        <SectionHeader
          title="沉淀进度"
          description="点击每一步可展开查看输入、真实稿件和拆解结果。"
        />
        <div className="operator-step-list">
          <ProgressDisclosure
            title="识别分享链接"
            summary={
              linkTask
                ? "已确认素材来源"
                : isExtracting
                  ? "正在读取分享内容"
                  : "等待粘贴抖音分享文案或链接"
            }
            state={
              extractionFailed
                ? "failed"
                : linkTask
                  ? "complete"
                  : isExtracting
                    ? "active"
                    : "waiting"
            }
          >
            <dl className="progress-detail-list">
              <div>
                <dt>提交内容</dt>
                <dd>{url.trim() || "尚未提交"}</dd>
              </div>
              <div>
                <dt>识别结果</dt>
                <dd>
                  {hasFailed
                    ? "没有取得可分析的视频内容"
                    : linkTask
                      ? "已确认视频内容，可以继续提取稿件"
                      : "主站处理后将在这里显示结果"}
                </dd>
              </div>
            </dl>
          </ProgressDisclosure>

          <ProgressDisclosure
            title="提取真实稿件"
            summary={
              hasTranscript
                ? `已拿到 ${transcriptText.trim().length} 字视频稿件`
                : isExtracting
                  ? "识别链接后自动开始"
                  : "没有真实稿件前不拆解"
            }
            state={
              hasFailed ? "failed" : hasTranscript ? "complete" : "waiting"
            }
          >
            {hasTranscript ? (
              <article
                className="manuscript-document"
                aria-label="提取到的视频稿件"
              >
                <header>
                  <span>
                    {qualityNeedsReview ? "AI 转写稿 · 待校正" : "AI 校正稿"}
                  </span>
                  <strong>{sourceVideo?.title || "视频稿件"}</strong>
                  <small>
                    {[sourceVideo?.author, `${transcriptText.trim().length} 字`]
                      .filter(Boolean)
                      .join(" · ")}
                  </small>
                </header>
                <div className="manuscript-body">
                  <h4>
                    {qualityNeedsReview ? "待确认稿件" : "校正后视频稿件"}
                  </h4>
                  {transcriptParagraphs.map((paragraph, index) => (
                    <p key={`${index}-${paragraph.slice(0, 12)}`}>
                      {paragraph}
                    </p>
                  ))}
                </div>
              </article>
            ) : (
              <p className="progress-empty-detail">
                {isExtracting
                  ? loadingMessage
                  : "主站转写完成后，可在这里按语义段落阅读全文。"}
              </p>
            )}
            {videoUpload?.transcript_quality_message ? (
              <div
                className={`transcript-quality-summary ${qualityNeedsReview ? "is-review" : "is-passed"}`}
              >
                <strong>
                  {qualityNeedsReview
                    ? "质量门禁未通过"
                    : `校正质量 ${videoUpload.transcript_quality_score} 分`}
                </strong>
                <span>{videoUpload.transcript_quality_message}</span>
              </div>
            ) : null}
            {videoUpload?.corrections?.length ? (
              <div
                className="transcript-correction-list"
                aria-label="自动校正记录"
              >
                {videoUpload.corrections.map((item, index) => (
                  <div key={`${item.original}-${item.corrected}-${index}`}>
                    <span>
                      <del>{item.original}</del>
                      <ArrowRight size={13} />
                      <strong>{item.corrected}</strong>
                    </span>
                    <small>
                      {item.reason} · {item.confidence}%
                    </small>
                  </div>
                ))}
              </div>
            ) : null}
            {videoUpload?.unresolved_fragments?.length ? (
              <div className="transcript-unresolved">
                <strong>仍需确认</strong>
                {videoUpload.unresolved_fragments.map((item) => (
                  <span key={item}>{item}</span>
                ))}
              </div>
            ) : null}
            {qualityNeedsReview && hasTranscript ? (
              <div className="transcript-review-editor">
                <label htmlFor="confirmed-transcript">确认后的视频稿件</label>
                <textarea
                  id="confirmed-transcript"
                  value={reviewText}
                  onChange={(event) => setReviewText(event.target.value)}
                  rows={12}
                />
                <div className="transcript-review-actions">
                  <label className="transcript-review-confirmation">
                    <input
                      type="checkbox"
                      checked={reviewConfirmed}
                      onChange={(event) =>
                        setReviewConfirmed(event.target.checked)
                      }
                    />
                    <span>
                      我已核对人名、数字和专业词；这份稿件可用于 Skill 分析。
                    </span>
                  </label>
                  <button
                    type="button"
                    className="primary-button"
                    disabled={
                      loading ||
                      reviewText.trim().length < 10 ||
                      !reviewConfirmed
                    }
                    onClick={() => onConfirmTranscript(reviewText)}
                  >
                    {loading ? (
                      <LoaderCircle className="button-spinner" size={16} />
                    ) : (
                      <CheckCircle2 size={16} />
                    )}
                    {loading ? "正在拆解..." : "核对完成，继续拆解"}
                  </button>
                </div>
              </div>
            ) : null}
          </ProgressDisclosure>

          <ProgressDisclosure
            title="拆解写作结构"
            summary={
              analysis
                ? "已生成写法拆解和 Skill 草稿"
                : isAnalyzing
                  ? "正在提炼可复用写法"
                  : "等待真实稿件"
            }
            state={
              analysis
                ? "complete"
                : isAnalyzing
                  ? "active"
                  : hasFailed
                    ? "failed"
                    : "waiting"
            }
          >
            {analysis ? (
              <dl className="progress-detail-list">
                <div>
                  <dt>开头方式</dt>
                  <dd>{analysis.analysis.hook}</dd>
                </div>
                <div>
                  <dt>信息推进</dt>
                  <dd>{analysis.analysis.conflict}</dd>
                </div>
                <div>
                  <dt>结尾方式</dt>
                  <dd>{analysis.analysis.ending_cta}</dd>
                </div>
                <div>
                  <dt>可借鉴动作</dt>
                  <dd>{analysis.preset_draft.borrowable_moves.join("；")}</dd>
                </div>
              </dl>
            ) : (
              <p className="progress-empty-detail">
                {isAnalyzing
                  ? loadingMessage
                  : "取得真实稿件后，才会分析开头、推进、情绪节奏和结尾。"}
              </p>
            )}
          </ProgressDisclosure>

          <ProgressDisclosure
            title="保存为 Skill"
            summary={
              analysis ? "拆解完成，等待你确认" : "提取并拆解成功后可保存"
            }
            state={analysis ? "ready" : "waiting"}
          >
            {analysis ? (
              <dl className="progress-detail-list">
                <div>
                  <dt>Skill 草稿</dt>
                  <dd>{analysis.preset_draft.name}</dd>
                </div>
                <div>
                  <dt>解决问题</dt>
                  <dd>
                    {analysis.preset_draft.solves_problems?.join("；") ||
                      "等待确认"}
                  </dd>
                </div>
                <div>
                  <dt>下一步</dt>
                  <dd>
                    确认结构能力名、适用输入和复用边界，然后保存进 Skill 库。
                  </dd>
                </div>
              </dl>
            ) : (
              <p className="progress-empty-detail">
                拆解完成后，这里会展示待确认的 Skill
                草稿，不会未经确认自动入库。
              </p>
            )}
          </ProgressDisclosure>
        </div>
      </Card>

      <Card>
        <SectionHeader
          title="可复用写作能力"
          description="主产出是团队以后能复用的文本结构，不是本次视频摘要。"
        />
        {analysis ? (
          <div className="analysis-preview">
            <span className="eyebrow-text">结构能力短名</span>
            <p>{analysis.preset_draft.name}</p>
            <span className="eyebrow-text">这个结构优秀在哪里</span>
            <div className="skill-asset-list">
              {(analysis.preset_draft.borrowable_moves.length
                ? analysis.preset_draft.borrowable_moves
                : analysis.preset_draft.skeleton
              )
                .slice(0, 3)
                .map((item) => (
                  <strong key={item}>{item}</strong>
                ))}
            </div>
            <span className="eyebrow-text">可迁移写法</span>
            <p>{analysis.preset_draft.hook_formula}</p>
            <span className="eyebrow-text">适合复用的结构条件</span>
            <div className="chip-row">
              {(analysis.preset_draft.applicable_scenes?.length
                ? analysis.preset_draft.applicable_scenes
                : [analysis.preset_draft.account_type]
              )
                .slice(0, 4)
                .map((item) => (
                  <Badge key={item}>{item}</Badge>
                ))}
            </div>
            <span className="eyebrow-text">不适合复用的边界</span>
            <p>
              {analysis.preset_draft.unsuitable_scenes
                ?.slice(0, 2)
                .join(" / ") || analysis.preset_draft.risk_boundary}
            </p>
            <details className="source-evidence-panel">
              <summary>来源证据</summary>
              <div>
                <span>来源标题</span>
                <strong>{analysis.source_video.title}</strong>
                <span>原视频开头</span>
                <p>{analysis.analysis.hook}</p>
                <span>真实稿件</span>
                <p>
                  {manuscriptParagraphs(transcriptText)
                    .slice(0, 2)
                    .join("\n\n") || "暂无可展示稿件"}
                </p>
              </div>
            </details>
            <button
              type="button"
              className="primary-button analysis-result-button"
              onClick={onViewAnalysis}
            >
              确认并保存 Skill
              <ArrowRight size={16} />
            </button>
          </div>
        ) : (
          <EmptyState
            title="还没有 Skill 草稿"
            description="真实提取到视频稿件后，系统会拆解文本结构、可借鉴写法和复用边界。"
          />
        )}
      </Card>
    </div>
  );
}
