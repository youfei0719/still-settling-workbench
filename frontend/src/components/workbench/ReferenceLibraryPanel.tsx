import { Card, EmptyState, SectionHeader } from "./ui"

/**
 * 参考稿库：Phase 6 会接入 manuscript-extractor 产物与人工保存的真人参考稿，
 * 用于 few-shot 表达参考（只学推进 / 节奏 / 开头转折结尾，不复制事实与句子）。
 */
export function ReferenceLibraryPanel() {
  return (
    <div className="page-grid">
      <Card className="writing-panel">
        <SectionHeader
          title="参考稿库"
          description="收集已确认优秀的真人稿件，作为表达方式的参考（few-shot）。"
        />
        <EmptyState
          title="参考稿库将在 Phase 6 接入"
          description="当前阶段先把创作主线跑通。届时的参考稿来自「稿件提取」产物和人工保存的优秀营销号稿件，只学习信息推进、句子节奏、开头和转折方式，不复制原稿事实、句子和观点。"
        />
      </Card>
    </div>
  )
}
