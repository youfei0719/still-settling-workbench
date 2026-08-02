import type { VideoUploadResponse } from "@/types/workbench"

const LOCAL_CONNECTOR_URL = "http://127.0.0.1:8765"

export class LocalConnectorUnavailableError extends Error {}

export class LocalConnectorExtractionError extends Error {}

function responseFileName(response: Response) {
  const header = response.headers.get("Content-Disposition") || ""
  const match = header.match(/filename="?([^";]+)"?/i)
  return match?.[1] || `douyin-${Date.now()}.mp4`
}

export async function extractWithLocalConnector(url: string): Promise<File> {
  let response: Response
  try {
    response = await fetch(`${LOCAL_CONNECTOR_URL}/v1/extract`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
      credentials: "omit",
    })
  } catch {
    throw new LocalConnectorUnavailableError(
      "本机提取连接器未启动，正在尝试服务器提取。",
    )
  }

  if (!response.ok) {
    let message = "本机连接器没有返回可用视频。"
    try {
      const payload = (await response.json()) as { error?: unknown }
      if (typeof payload.error === "string") message = payload.error
    } catch {
      // Keep the safe generic message for non-JSON local connector failures.
    }
    throw new LocalConnectorExtractionError(message)
  }

  const file = await response.blob()
  if (!file.size) {
    throw new LocalConnectorExtractionError("本机连接器返回了空视频文件。")
  }
  return new File([file], responseFileName(response), {
    type: response.headers.get("Content-Type") || "video/mp4",
  })
}

export async function extractAndUploadWithLocalConnector(
  url: string,
  uploadUrl: string,
  authorization?: string,
): Promise<VideoUploadResponse> {
  let response: Response
  try {
    response = await fetch(`${LOCAL_CONNECTOR_URL}/v1/extract-and-upload`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, upload_url: uploadUrl, authorization }),
      credentials: "omit",
    })
  } catch {
    throw new LocalConnectorUnavailableError(
      "本机提取连接器未启动，正在尝试服务器提取。",
    )
  }

  if (!response.ok) {
    let message = "本机连接器没有返回可用视频。"
    try {
      const payload = (await response.json()) as { error?: unknown }
      if (typeof payload.error === "string") message = payload.error
    } catch {
      // Keep the safe generic message for non-JSON local connector failures.
    }
    throw new LocalConnectorExtractionError(message)
  }

  return response.json() as Promise<VideoUploadResponse>
}
