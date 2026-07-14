import { useState } from 'react'
import { CalendarDays } from 'lucide-react'
import {
  startOfLocalDay,
  endOfLocalDay,
  type DateRange,
  NO_DATE_RANGE
} from '../../lib/conversations/filtering'

// ms → 'yyyy-mm-dd' (local) for a native <input type="date">.
function toInputValue(ms: number | null): string {
  if (ms == null) return ''
  const d = new Date(ms)
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

function parseInputDate(v: string): Date | null {
  if (!v) return null
  const [y, m, d] = v.split('-').map(Number)
  if (!y || !m || !d) return null
  return new Date(y, m - 1, d)
}

// A "Date" filter control: a button that opens a popover with native start/end
// date pickers. Emits an inclusive [startOfDay, endOfDay] range in epoch ms.
export function DateFilterButton({
  dateRange,
  onChange
}: {
  dateRange: DateRange
  onChange: (range: DateRange) => void
}): React.JSX.Element {
  const [open, setOpen] = useState(false)
  const active = dateRange.start != null || dateRange.end != null

  const setStart = (v: string): void => {
    const d = parseInputDate(v)
    onChange({ start: d ? startOfLocalDay(d.getTime()) : null, end: dateRange.end })
  }
  const setEnd = (v: string): void => {
    const d = parseInputDate(v)
    onChange({ start: dateRange.start, end: d ? endOfLocalDay(d.getTime()) : null })
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className={`surface-panel flex items-center gap-2 px-4 py-2.5 text-sm transition-colors duration-200 ${
          active ? 'text-white' : 'text-white/55 hover:text-white/80'
        }`}
        title="Filter by date"
      >
        <CalendarDays className="h-4 w-4" />
        <span className="hidden sm:inline">Date</span>
        {active && <span className="h-1.5 w-1.5 rounded-full bg-white" />}
      </button>

      {open && (
        <>
          {/* Outside-click catcher. */}
          <div className="fixed inset-0 z-[90]" onClick={() => setOpen(false)} />
          <div className="surface-panel absolute right-0 z-[100] mt-2 w-64 p-4">
            <label className="block text-xs font-medium text-white/50">From</label>
            <input
              type="date"
              value={toInputValue(dateRange.start)}
              max={toInputValue(dateRange.end) || undefined}
              onChange={(e) => setStart(e.target.value)}
              className="input-field mt-1.5 py-2 [color-scheme:dark]"
            />
            <label className="mt-3 block text-xs font-medium text-white/50">To</label>
            <input
              type="date"
              value={toInputValue(dateRange.end)}
              min={toInputValue(dateRange.start) || undefined}
              onChange={(e) => setEnd(e.target.value)}
              className="input-field mt-1.5 py-2 [color-scheme:dark]"
            />
            {active && (
              <button
                onClick={() => onChange(NO_DATE_RANGE)}
                className="mt-3 text-xs font-medium text-white/55 transition-colors hover:text-white"
              >
                Clear dates
              </button>
            )}
          </div>
        </>
      )}
    </div>
  )
}
