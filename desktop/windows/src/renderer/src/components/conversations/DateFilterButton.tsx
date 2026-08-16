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
  const fromValue = toInputValue(dateRange.start)
  const toValue = toInputValue(dateRange.end)

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
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-white/50">Date range</span>
              {/* Always offered while a range is set — the only way to undo one. */}
              {active && (
                <button
                  onClick={() => onChange(NO_DATE_RANGE)}
                  className="rounded-md px-1.5 py-0.5 text-xs font-medium text-white/55 transition-colors hover:bg-white/10 hover:text-white"
                >
                  Clear
                </button>
              )}
            </div>
            <label className="mt-2.5 block text-xs font-medium text-white/50" htmlFor="date-from">
              From
            </label>
            <input
              id="date-from"
              type="date"
              value={fromValue}
              data-empty={fromValue === ''}
              max={toValue || undefined}
              onChange={(e) => setStart(e.target.value)}
              className="date-input mt-1.5 py-2"
            />
            <label className="mt-3 block text-xs font-medium text-white/50" htmlFor="date-to">
              To
            </label>
            <input
              id="date-to"
              type="date"
              value={toValue}
              data-empty={toValue === ''}
              min={fromValue || undefined}
              onChange={(e) => setEnd(e.target.value)}
              className="date-input mt-1.5 py-2"
            />
          </div>
        </>
      )}
    </div>
  )
}
