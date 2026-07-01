import { parseTemporalReference, extractSearchTerms } from './temporalParser'

export async function getScreenHistoryContext(message: string): Promise<string> {
  // Parse temporal reference from the message
  const temporalRef = parseTemporalReference(message)
  
  // If no temporal reference, check for keywords that suggest screen history
  if (!temporalRef) {
    const historyKeywords = [
      'saw', 'seen', 'was on', 'showed', 'displayed',
      'error', 'message', 'screen', 'window',
      'earlier', 'before', 'previously'
    ]
    
    const lowerMessage = message.toLowerCase()
    const hasHistoryKeyword = historyKeywords.some(keyword => lowerMessage.includes(keyword))
    
    if (!hasHistoryKeyword) {
      return ''
    }
    
    // Default to last 30 minutes if talking about screen but no specific time
    const defaultRange = {
      startTime: Date.now() - 30 * 60 * 1000,
      endTime: Date.now(),
      description: 'recent'
    }
    
    // Extract search terms without temporal phrases for better search
    const searchTerms = extractSearchTerms(message)
    return fetchScreenContext(defaultRange.startTime, defaultRange.endTime, searchTerms || undefined)
  }
  
  // Extract search terms after removing temporal phrases
  const searchTerms = extractSearchTerms(message)
  
  // Fetch screen context for the identified time range
  return fetchScreenContext(temporalRef.startTime, temporalRef.endTime, searchTerms)
}

async function fetchScreenContext(
  startTime: number, 
  endTime: number, 
  searchQuery?: string
): Promise<string> {
  try {
    // Search screen history
    const result = await window.omi.screenSearchHistory({
      startTime,
      endTime,
      searchQuery: searchQuery || undefined,
      limit: 10
    })
    
    if (!result || result.frames.length === 0) {
      return ''
    }
    
    // Format context for the AI
    const lines: string[] = [
      `[Screen history context from ${result.timeRange.description}]`,
      result.summary
    ]
    
    // Add detailed frame information for top results
    const topFrames = result.frames.slice(0, 5)
    if (topFrames.length > 0) {
      lines.push('\nDetailed screen captures:')
      
      for (const frame of topFrames) {
        const time = new Date(frame.ts).toLocaleTimeString()
        const app = frame.app || 'Unknown app'
        const title = frame.windowTitle || 'No title'
        
        lines.push(`\n[${time}] ${app} - ${title}`)
        
        if (frame.ocrText) {
          // Include relevant portion of OCR text
          let ocrPreview = frame.ocrText.trim()
          
          // If searching for something specific, find that context
          if (searchQuery) {
            const lowerOcr = ocrPreview.toLowerCase()
            const lowerQuery = searchQuery.toLowerCase()
            const index = lowerOcr.indexOf(lowerQuery)
            
            if (index !== -1) {
              // Extract context around the match
              const contextStart = Math.max(0, index - 100)
              const contextEnd = Math.min(ocrPreview.length, index + searchQuery.length + 100)
              ocrPreview = '...' + ocrPreview.substring(contextStart, contextEnd) + '...'
            }
          }
          
          // Limit OCR text length
          if (ocrPreview.length > 300) {
            ocrPreview = ocrPreview.substring(0, 300) + '...'
          }
          
          lines.push(ocrPreview)
        }
      }
    }
    
    return lines.join('\n')
  } catch (error) {
    console.error('Failed to fetch screen history context:', error)
    return ''
  }
}

export function isAskingAboutScreenHistory(message: string): boolean {
  const lowerMessage = message.toLowerCase()
  
  // Check for temporal references
  if (parseTemporalReference(message)) {
    // Has temporal reference, check if it's about screens/visual content
    const screenKeywords = ['saw', 'seen', 'screen', 'showed', 'error', 'message', 'window', 'displayed']
    return screenKeywords.some(keyword => lowerMessage.includes(keyword))
  }
  
  // Check for direct screen history questions
  const historyPatterns = [
    /what.*(was|were).*on.*screen/,
    /what.*did.*i.*see/,
    /show.*me.*what.*was/,
    /error.*message/,
    /that.*(error|message|screen)/,
    /find.*what.*showed/
  ]
  
  return historyPatterns.some(pattern => pattern.test(lowerMessage))
}