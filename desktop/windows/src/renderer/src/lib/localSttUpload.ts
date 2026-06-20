import { omiApi } from './apiClient'
import type { TranscriptLine } from '../../../shared/types'

type UploadSegment = {
  text: string
  speaker: string
  speaker_id?: number
  is_user: boolean
  person_id?: string
  start: number
  end: number
}

type UploadResponse = {
  id: string
  status: string
  discarded: boolean
}

function parseSpeakerId(speaker: string | undefined): number | undefined {
  if (!speaker) return undefined
  const match = speaker.match(/(\d+)/)
  if (!match) return undefined
  const parsed = Number(match[1])
  return Number.isFinite(parsed) ? parsed : undefined
}

function fallbackEnd(start: number, text: string): number {
  const words = text.trim().split(/\s+/).filter(Boolean).length
  return start + Math.max(0.5, words * 0.35)
}

export function buildUploadSegments(lines: TranscriptLine[]): UploadSegment[] {
  const raw: UploadSegment[] = []
  let cursor = 0

  for (const line of lines) {
    const text = line.text.trim()
    if (!text) continue

    const start =
      typeof line.start === 'number' && Number.isFinite(line.start) ? line.start : cursor
    const end =
      typeof line.end === 'number' && Number.isFinite(line.end) && line.end > start
        ? line.end
        : fallbackEnd(start, text)
    cursor = Math.max(cursor, end)

    const isUser = line.isUser ?? line.speaker === 'You'
    const speakerId = line.speakerId ?? parseSpeakerId(line.speaker) ?? (isUser ? 0 : undefined)
    const speaker =
      line.speaker && line.speaker !== 'You'
        ? line.speaker
        : typeof speakerId === 'number'
          ? `SPEAKER_${speakerId}`
          : 'SPEAKER_00'

    raw.push({
      text,
      speaker,
      speaker_id: speakerId,
      is_user: isUser,
      person_id: line.personId,
      start,
      end
    })
  }

  const merged: UploadSegment[] = []
  for (const segment of raw.sort((a, b) => a.start - b.start)) {
    const prev = merged[merged.length - 1]
    if (
      prev &&
      prev.speaker === segment.speaker &&
      prev.speaker_id === segment.speaker_id &&
      prev.is_user === segment.is_user &&
      prev.person_id === segment.person_id &&
      segment.start - prev.end <= 1.0
    ) {
      prev.text = `${prev.text} ${segment.text}`.trim()
      prev.end = Math.max(prev.end, segment.end)
      continue
    }
    merged.push({ ...segment })
  }

  return merged.slice(0, 500)
}

export async function uploadConversationFromSegments(args: {
  lines: TranscriptLine[]
  startedAt: number
  finishedAt: number
  language: string
}): Promise<UploadResponse | null> {
  const transcript_segments = buildUploadSegments(args.lines)
  if (transcript_segments.length === 0) return null

  const latestEnd = Math.max(...transcript_segments.map((s) => s.end))
  const finishedAt = Math.max(
    args.finishedAt,
    args.startedAt + latestEnd * 1000,
    args.startedAt + 1000
  )
  const response = await omiApi.post<UploadResponse>('/v1/conversations/from-segments', {
    transcript_segments,
    source: 'desktop',
    started_at: new Date(args.startedAt).toISOString(),
    finished_at: new Date(finishedAt).toISOString(),
    language: args.language
  })
  return response.data
}
