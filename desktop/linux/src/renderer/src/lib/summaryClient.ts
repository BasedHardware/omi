// src/renderer/src/lib/summaryClient.ts
// Extract summaries and action items from transcript text using Gemini (via Omi proxy)
import { generate } from './geminiClient'
import type { TranscriptLine } from '../../../shared/types'

export type SummaryResult = {
  summary: string
  tasks: string[]
  keyPoints: string[]
}

export async function extractSummary(lines: TranscriptLine[]): Promise<SummaryResult> {
  if (lines.length === 0) {
    return { summary: 'No transcript available.', tasks: [], keyPoints: [] }
  }

  const transcript = lines.map((l) => `${l.speaker || 'Speaker'}: ${l.text}`).join('\n')

  const response = await generate({
    model: 'gemini-2.5-flash',
    parts: [
      {
        text: `Analyze this conversation transcript and extract:
1. A concise summary (2-3 sentences)
2. Action items / tasks mentioned (as a list)
3. Key points discussed (as a list)

Transcript:
${transcript}

Respond in JSON format:
{
  "summary": "...",
  "tasks": ["task 1", "task 2"],
  "keyPoints": ["point 1", "point 2"]
}`
      }
    ],
    systemPrompt: 'You are a helpful assistant that extracts summaries and action items from conversations. Be concise and practical.',
    responseSchema: {
      type: 'object',
      properties: {
        summary: { type: 'string' },
        tasks: { type: 'array', items: { type: 'string' } },
        keyPoints: { type: 'array', items: { type: 'string' } }
      },
      required: ['summary', 'tasks', 'keyPoints']
    }
  })

  try {
    // Parse the JSON response
    const cleaned = response.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim()
    return JSON.parse(cleaned) as SummaryResult
  } catch {
    // If JSON parsing fails, return the raw text as summary
    return {
      summary: response || 'Failed to generate summary.',
      tasks: [],
      keyPoints: []
    }
  }
}
