export type ConversationSummary = {
  title?: string | null
  capturedAt?: string | null
  overview?: string | null
  actionItems?: readonly { description: string; completed?: boolean }[] | null
}

// Titles and task descriptions are plain text; keep embedded newlines or Markdown
// punctuation from turning them into extra headings, links, or task checkboxes.
function inlineText(value: string): string {
  return value
    .trim()
    .replace(/\s+/g, ' ')
    .replace(/[\\`*_[\]<>]/g, '\\$&')
}

/** Export only the summary already on screen. Never fetch or generate content. */
export function formatConversationSummaryMarkdown(
  summary: ConversationSummary,
  options: { locale?: string; timeZone?: string } = {}
): string {
  const sections = [`### 💡 ${inlineText(summary.title || '') || 'Conversation'}`]
  const captured = summary.capturedAt ? new Date(summary.capturedAt) : null
  if (captured && Number.isFinite(captured.getTime())) {
    const when = new Intl.DateTimeFormat(options.locale, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      timeZoneName: 'longOffset',
      timeZone: options.timeZone
    }).format(captured)
    sections.push(`*Captured via Omi • ${when}*`)
  }
  const overview = summary.overview?.trim()
  if (overview) sections.push(`**Key Takeaways:**\n\n${overview}`)
  const tasks = (summary.actionItems ?? [])
    .filter((item) => item.description.trim())
    .map((item) => `- [${item.completed ? 'x' : ' '}] ${inlineText(item.description)}`)
  if (tasks.length) sections.push(`**Action Items:**\n\n${tasks.join('\n')}`)
  return sections.join('\n\n')
}
