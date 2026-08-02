const LOCAL_CONNECTOR_URL = "http://127.0.0.1:8765"

export class LocalConnectorUnavailableError extends Error {}

export class LocalConnectorExtractionError extends Error {}

export interface LocalTranscriptResponse {
  source_url: string
  title: string
  text: string
  timestamps: string[]
  provider: string
  media_retention: "deleted_after_transcription"
  message: string
}

export async function extractAndTranscribeWithLocalConnector(
  url: string,
): Promise<LocalTranscriptResponse> {
  let response: Response
  try {
    response = await fetch(`${LOCAL_CONNECTOR_URL}/v1/extract-and-transcribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
      credentials: "omit",
    })
  } catch {
    throw new LocalConnectorUnavailableError(
      "本机媒体连接器未启动。为避免把视频上传到服务器，工作台不会改由云端下载；请启动本机连接器后重试。",
    )
  }

  if (!response.ok) {
    let message = "本机连接器没有返回可用文稿。"
    try {
      const payload = (await response.json()) as { error?: unknown }
      if (typeof payload.error === "string") message = payload.error
    } catch {
      // Preserve the generic message for non-JSON local failures.
    }
    throw new LocalConnectorExtractionError(message)
  }

  const payload = (await response.json()) as Partial<LocalTranscriptResponse>
  if (
    typeof payload.text !== "string" ||
    payload.text.trim().length < 10 ||
    typeof payload.source_url !== "string" ||
    typeof payload.provider !== "string"
  ) {
    throw new LocalConnectorExtractionError("本机连接器返回的文稿不完整。")
  }
  return {
    source_url: payload.source_url,
    title:
      typeof payload.title === "string" && payload.title.trim()
        ? payload.title
        : "本机转写的抖音视频",
    text: payload.text.trim(),
    timestamps: Array.isArray(payload.timestamps)
      ? payload.timestamps.filter(
          (item): item is string => typeof item === "string",
        )
      : [],
    provider: payload.provider,
    media_retention: "deleted_after_transcription",
    message:
      typeof payload.message === "string"
        ? payload.message
        : "本机媒体已处理，云端仅接收文稿。",
  }
}
