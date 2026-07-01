import { ipcMain } from 'electron'
import { searchRewindFramesInTimeRange } from './db'
import type { RewindFrame } from '../../shared/types'

interface ScreenHistorySearchParams {
  startTime: number
  endTime: number
  searchQuery?: string
  limit?: number
}

interface ScreenHistoryResult {
  frames: RewindFrame[]
  summary: string
  timeRange: {
    start: number
    end: number
    description: string
  }
}

async function searchScreenHistory(params: ScreenHistorySearchParams): Promise<ScreenHistoryResult> {
  const { startTime, endTime, searchQuery, limit = 20 } = params

  // Search the database for frames in the time range
  const frames = searchRewindFramesInTimeRange(startTime, endTime, searchQuery, limit)

  // Generate a summary of findings
  let summary = ''
  if (frames.length === 0) {
    summary = 'No screen activity found in the specified time range.'
  } else {
    // Group frames by app for summary
    const appCounts = new Map<string, number>()
    const windowTitles = new Set<string>()
    const snippets: string[] = []

    for (const frame of frames) {
      // Count apps
      const app = frame.app || 'Unknown'
      appCounts.set(app, (appCounts.get(app) || 0) + 1)
      
      // Collect window titles
      if (frame.windowTitle) {
        windowTitles.add(frame.windowTitle)
      }

      // Collect relevant OCR snippets if searching for something specific
      if (searchQuery && frame.ocrText) {
        const lowerOcr = frame.ocrText.toLowerCase()
        const lowerQuery = searchQuery.toLowerCase()
        const index = lowerOcr.indexOf(lowerQuery)
        if (index !== -1) {
          // Extract context around the match
          const contextStart = Math.max(0, index - 50)
          const contextEnd = Math.min(frame.ocrText.length, index + searchQuery.length + 50)
          const snippet = frame.ocrText.substring(contextStart, contextEnd).trim()
          if (snippets.length < 3) {
            snippets.push(`[${frame.app}] ...${snippet}...`)
          }
        }
      }
    }

    // Build summary
    const appSummary = Array.from(appCounts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([app, count]) => `${app} (${count})`)
      .join(', ')

    summary = `Found ${frames.length} screen captures. Apps: ${appSummary}.`
    
    // Add window titles to summary if no OCR available
    if (windowTitles.size > 0 && snippets.length === 0) {
      const titleList = Array.from(windowTitles).slice(0, 5).join(', ')
      summary += `\nWindows: ${titleList}`
    }

    if (snippets.length > 0) {
      summary += '\n\nRelevant text snippets:\n' + snippets.join('\n')
    }
  }

  return {
    frames,
    summary,
    timeRange: {
      start: startTime,
      end: endTime,
      description: `${new Date(startTime).toLocaleString()} - ${new Date(endTime).toLocaleString()}`
    }
  }
}

async function getScreenContextForTimeRange(
  startTime: number,
  endTime: number,
  maxFrames = 5
): Promise<string> {
  const frames = searchRewindFramesInTimeRange(startTime, endTime, undefined, maxFrames)

  if (frames.length === 0) {
    return ''
  }

  const lines: string[] = [
    `[Screen history from ${new Date(startTime).toLocaleTimeString()} to ${new Date(
      endTime
    ).toLocaleTimeString()}]`
  ]

  for (const frame of frames) {
    const time = new Date(frame.ts).toLocaleTimeString()
    const app = frame.app || 'Unknown'
    const title = frame.windowTitle ? ` - ${frame.windowTitle}` : ''
    
    lines.push(`\n${time} | ${app}${title}`)
    
    if (frame.ocrText && frame.ocrText.trim()) {
      // Include first 200 chars of OCR text
      const preview = frame.ocrText.trim().substring(0, 200)
      lines.push(preview + (frame.ocrText.length > 200 ? '...' : ''))
    }
  }

  return lines.join('\n')
}

export function registerScreenHistoryHandlers(): void {
  ipcMain.handle('screen:searchHistory', async (_e, params: ScreenHistorySearchParams) => {
    return searchScreenHistory(params)
  })

  ipcMain.handle(
    'screen:getHistoryContext',
    async (_e, startTime: number, endTime: number, maxFrames?: number) => {
      return getScreenContextForTimeRange(startTime, endTime, maxFrames)
    }
  )
}