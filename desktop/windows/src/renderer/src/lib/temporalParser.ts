interface TimeRange {
  startTime: number
  endTime: number
  description: string
}

export function parseTemporalReference(query: string, currentTime: number = Date.now()): TimeRange | null {
  const lowerQuery = query.toLowerCase()
  
  // Match "X minutes ago"
  const minutesAgoMatch = lowerQuery.match(/(\d+)\s*minutes?\s*ago/)
  if (minutesAgoMatch) {
    const minutes = parseInt(minutesAgoMatch[1], 10)
    const targetTime = currentTime - minutes * 60 * 1000
    // Return a 5-minute window around the target time
    return {
      startTime: targetTime - 2.5 * 60 * 1000,
      endTime: targetTime + 2.5 * 60 * 1000,
      description: `${minutes} minute${minutes === 1 ? '' : 's'} ago`
    }
  }

  // Match "X hours ago"
  const hoursAgoMatch = lowerQuery.match(/(\d+)\s*hours?\s*ago/)
  if (hoursAgoMatch) {
    const hours = parseInt(hoursAgoMatch[1], 10)
    const targetTime = currentTime - hours * 60 * 60 * 1000
    // Return the full hour window
    const startOfHour = new Date(targetTime)
    startOfHour.setMinutes(0, 0, 0)
    const endOfHour = new Date(targetTime)
    endOfHour.setMinutes(59, 59, 999)
    return {
      startTime: startOfHour.getTime(),
      endTime: endOfHour.getTime(),
      description: `${hours} hour${hours === 1 ? '' : 's'} ago`
    }
  }

  // Match "today"
  if (lowerQuery.includes('today')) {
    const startOfDay = new Date(currentTime)
    startOfDay.setHours(0, 0, 0, 0)
    const endOfDay = new Date(currentTime)
    endOfDay.setHours(23, 59, 59, 999)
    return {
      startTime: startOfDay.getTime(),
      endTime: endOfDay.getTime(),
      description: 'today'
    }
  }

  // Match "yesterday"
  if (lowerQuery.includes('yesterday')) {
    const yesterday = new Date(currentTime)
    yesterday.setDate(yesterday.getDate() - 1)
    yesterday.setHours(0, 0, 0, 0)
    const endOfYesterday = new Date(yesterday)
    endOfYesterday.setHours(23, 59, 59, 999)
    return {
      startTime: yesterday.getTime(),
      endTime: endOfYesterday.getTime(),
      description: 'yesterday'
    }
  }

  // Match "this morning", "this afternoon", "this evening"
  if (lowerQuery.includes('this evening')) {
    const startOfEvening = new Date(currentTime)
    startOfEvening.setHours(18, 0, 0, 0)
    const endOfEvening = new Date(currentTime)
    endOfEvening.setHours(23, 59, 59, 999)
    return {
      startTime: startOfEvening.getTime(),
      endTime: endOfEvening.getTime(),
      description: 'this evening'
    }
  }

  if (lowerQuery.includes('this morning')) {
    const startOfMorning = new Date(currentTime)
    startOfMorning.setHours(6, 0, 0, 0)
    const endOfMorning = new Date(currentTime)
    endOfMorning.setHours(11, 59, 59, 999)
    return {
      startTime: startOfMorning.getTime(),
      endTime: endOfMorning.getTime(),
      description: 'this morning'
    }
  }

  if (lowerQuery.includes('this afternoon')) {
    const startOfAfternoon = new Date(currentTime)
    startOfAfternoon.setHours(12, 0, 0, 0)
    const endOfAfternoon = new Date(currentTime)
    endOfAfternoon.setHours(17, 59, 59, 999)
    return {
      startTime: startOfAfternoon.getTime(),
      endTime: endOfAfternoon.getTime(),
      description: 'this afternoon'
    }
  }

  // Match "last week"
  if (lowerQuery.includes('last week')) {
    const startOfWeek = new Date(currentTime)
    startOfWeek.setDate(startOfWeek.getDate() - 7)
    startOfWeek.setHours(0, 0, 0, 0)
    return {
      startTime: startOfWeek.getTime(),
      endTime: currentTime,
      description: 'last week'
    }
  }

  // Match "recently" or "just now"
  if (lowerQuery.includes('recently') || lowerQuery.includes('just now') || lowerQuery.includes('just saw')) {
    return {
      startTime: currentTime - 10 * 60 * 1000, // Last 10 minutes
      endTime: currentTime,
      description: 'recently'
    }
  }

  // Match "earlier"
  if (lowerQuery.includes('earlier')) {
    const startOfDay = new Date(currentTime)
    startOfDay.setHours(0, 0, 0, 0)
    return {
      startTime: startOfDay.getTime(),
      endTime: currentTime,
      description: 'earlier today'
    }
  }

  return null
}

export function extractSearchTerms(query: string): string {
  // Remove common temporal phrases
  const temporalPhrases = [
    /\d+\s*minutes?\s*ago/gi,
    /\d+\s*hours?\s*ago/gi,
    /\byesterday\b/gi,
    /\btoday\b/gi,
    /\bthis morning\b/gi,
    /\bthis afternoon\b/gi,
    /\bthis evening\b/gi,
    /\blast week\b/gi,
    /\brecently\b/gi,
    /\bjust now\b/gi,
    /\bjust saw\b/gi,
    /\bearlier\b/gi,
    /\bwhat was\b/gi,
    /\bwhat were\b/gi,
    /\bi saw\b/gi,
    /\bthat\b/gi,
    /\bthe\b/gi
  ]

  let cleanedQuery = query
  for (const phrase of temporalPhrases) {
    cleanedQuery = cleanedQuery.replace(phrase, ' ')
  }

  // Clean up extra spaces and trim
  return cleanedQuery.replace(/\s+/g, ' ').trim()
}