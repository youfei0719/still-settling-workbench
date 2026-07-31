export function speechCharacterCount(value: string) {
  return value.replace(/\s/g, "").length
}

export function estimatedSpeechSeconds(value: string) {
  return Math.max(1, Math.round(speechCharacterCount(value) / 4.8))
}

export function speechTargetRange(durationSeconds: number) {
  const minimum = Math.max(100, Math.round(durationSeconds * 4.5))
  const maximum = Math.max(minimum + 30, Math.round(durationSeconds * 5.3))
  const toleranceMinimum = Math.max(80, Math.round(durationSeconds * 3.5))
  const toleranceMaximum = Math.max(
    toleranceMinimum + 60,
    Math.round(durationSeconds * 6.5),
  )
  return { minimum, maximum, toleranceMinimum, toleranceMaximum }
}

export function speechLengthStatus(value: string, durationSeconds: number) {
  const count = speechCharacterCount(value)
  const estimatedSeconds = estimatedSpeechSeconds(value)
  const { minimum, maximum, toleranceMinimum, toleranceMaximum } =
    speechTargetRange(durationSeconds)
  const status =
    count < toleranceMinimum
      ? "short"
      : count > toleranceMaximum
        ? "long"
        : "ready"
  const pacing =
    count < minimum ? "shorter" : count > maximum ? "longer" : "on_target"
  return {
    count,
    estimatedSeconds,
    minimum,
    maximum,
    toleranceMinimum,
    toleranceMaximum,
    status,
    pacing,
  }
}

export function formatSpeechParagraphs(value: string) {
  const normalized = value.replace(/\r\n/g, "\n").trim()
  if (!normalized || normalized.includes("\n\n")) return normalized

  const sentences =
    normalized
      .match(/[^。！？!?\n]+[。！？!?]?/g)
      ?.map((item) => item.trim())
      .filter(Boolean) || []
  if (sentences.length < 3) return normalized

  const paragraphs: string[] = []
  let current = ""
  for (const sentence of sentences) {
    const next = current ? `${current}${sentence}` : sentence
    if (current && (next.length > 105 || current.length >= 70)) {
      paragraphs.push(current)
      current = sentence
    } else {
      current = next
    }
  }
  if (current) paragraphs.push(current)
  return paragraphs.join("\n\n")
}
