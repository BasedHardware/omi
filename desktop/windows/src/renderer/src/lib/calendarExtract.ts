// Synthesize upcoming Calendar events into actionable tasks through the backend
// connector-synthesis SSOT. formatCalendarItems is split out (pure) so the row
// rendering is unit-tested without the network.
import { synthesizeConnectorItems } from './connectorSynthesis'
import type { CalendarItem } from '../../../shared/types'

export type SynthesizedTask = { description: string; dueAt?: string }

export function formatCalendarItems(items: CalendarItem[]): string[] {
  return items.slice(0, 50).map((it) => {
    const start = it.startMs ? new Date(it.startMs).toISOString() : 'unknown'
    const loc = it.location ? ` @ ${it.location}` : ''
    return `${it.title}${loc} | starts ${start} | id=${it.id}`
  })
}

export async function extractCalendarTasks(items: CalendarItem[]): Promise<SynthesizedTask[]> {
  if (items.length === 0) return []
  const synthesis = await synthesizeConnectorItems('calendar', formatCalendarItems(items))
  return synthesis.tasks.map((t) => ({ description: t.description, dueAt: t.dueAt }))
}
