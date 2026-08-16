import { useMemo, useState } from 'react'
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react'
import { startOfLocalDay } from '../../lib/conversations/filtering'
import { MAC_PURPLE } from '../../lib/macPalette'

// The date-picker for the Rewind timeline: a button labelled `MMM d, yyyy` that
// opens a graphical month-grid calendar popover (macOS RewindPage.datePickerControls
// — a .graphical DatePicker). Selecting a day emits its local-midnight ms; the page
// reloads only when the day actually changes.
//
// Windows-native chrome, neutral palette — EXCEPT the selected day, which renders in
// Mac's purplePrimary (#8B5CF6). That is the sanctioned Track 4 exception (Mac ports
// its purple as-is where Mac renders purple); it stays contained to this one cell.

const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December'
]
const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']

/** `MMM d, yyyy` — e.g. "Jul 14, 2026". */
function buttonLabel(ms: number): string {
  const d = new Date(ms)
  return `${MONTHS[d.getMonth()].slice(0, 3)} ${d.getDate()}, ${d.getFullYear()}`
}

/** The calendar cells for a month: leading blanks (nulls) to the first weekday,
 *  then each day's local-midnight ms. */
function monthCells(year: number, month: number): (number | null)[] {
  const first = new Date(year, month, 1)
  const lead = first.getDay()
  const days = new Date(year, month + 1, 0).getDate()
  const cells: (number | null)[] = Array.from({ length: lead }, () => null)
  for (let d = 1; d <= days; d++) cells.push(new Date(year, month, d).getTime())
  return cells
}

export function RewindDatePicker({
  selectedDate,
  onSelect
}: {
  selectedDate: number
  onSelect: (dayMs: number) => void
}): React.JSX.Element {
  const [open, setOpen] = useState(false)
  const sel = new Date(selectedDate)
  const [viewYear, setViewYear] = useState(sel.getFullYear())
  const [viewMonth, setViewMonth] = useState(sel.getMonth())

  // Re-anchor the grid on the selected month each time the popover opens, so it
  // never lingers on a month the user paged to but didn't pick from.
  const toggle = (): void => {
    if (!open) {
      setViewYear(sel.getFullYear())
      setViewMonth(sel.getMonth())
    }
    setOpen((o) => !o)
  }

  const cells = useMemo(() => monthCells(viewYear, viewMonth), [viewYear, viewMonth])
  // eslint-disable-next-line react-hooks/purity -- "today" for the calendar ring is clock-relative by nature
  const today = startOfLocalDay(Date.now())

  const step = (delta: number): void => {
    const m = viewMonth + delta
    setViewYear(viewYear + Math.floor(m / 12))
    setViewMonth(((m % 12) + 12) % 12)
  }

  return (
    <div className="relative">
      <button
        onClick={toggle}
        className="inline-flex items-center gap-1.5 rounded-control border border-line bg-white/[0.06] px-3 py-1.5 text-sm text-white/80 transition-colors hover:border-line-strong hover:bg-white/[0.10] hover:text-white"
        title="Pick a day"
      >
        <CalendarDays className="h-4 w-4" />
        {buttonLabel(selectedDate)}
      </button>

      {open && (
        <>
          {/* Outside-click catcher. */}
          <div className="fixed inset-0 z-[90]" onClick={() => setOpen(false)} />
          <div
            data-testid="rewind-calendar"
            className="surface-panel absolute right-0 z-[100] mt-2 w-64 p-3"
          >
            <div className="mb-2 flex items-center justify-between">
              <button
                onClick={() => step(-1)}
                className="rounded p-1 text-white/60 transition-colors hover:bg-white/10 hover:text-white"
                title="Previous month"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <span className="text-sm font-medium text-white/90">
                {MONTHS[viewMonth]} {viewYear}
              </span>
              <button
                onClick={() => step(1)}
                className="rounded p-1 text-white/60 transition-colors hover:bg-white/10 hover:text-white"
                title="Next month"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
            <div className="grid grid-cols-7 gap-0.5 text-center">
              {WEEKDAYS.map((w) => (
                <div key={w} className="py-1 text-[10px] font-medium uppercase text-white/35">
                  {w}
                </div>
              ))}
              {cells.map((day, i) =>
                day == null ? (
                  <div key={`b-${i}`} />
                ) : (
                  <DayCell
                    key={day}
                    day={day}
                    selected={day === selectedDate}
                    isToday={day === today}
                    disabled={day > today}
                    onClick={() => {
                      onSelect(day)
                      setOpen(false)
                    }}
                  />
                )
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function DayCell({
  day,
  selected,
  isToday,
  disabled,
  onClick
}: {
  day: number
  selected: boolean
  isToday: boolean
  disabled: boolean
  onClick: () => void
}): React.JSX.Element {
  const label = new Date(day).getDate()
  const base =
    'flex h-8 w-8 items-center justify-center justify-self-center rounded-full text-xs transition-colors'
  if (disabled) {
    return (
      <button disabled data-day={label} className={`${base} cursor-default text-white/20`}>
        {label}
      </button>
    )
  }
  return (
    <button
      onClick={onClick}
      data-day={label}
      // Mac's selected-day purple, ported per the program UI ruling; contained (one
      // shared MAC_PURPLE constant, not a new global token — desktop/windows is
      // outside the INV-UI-1 brand ratchet).
      style={selected ? { backgroundColor: MAC_PURPLE } : undefined}
      className={`${base} ${
        selected
          ? 'font-medium text-white'
          : `text-white/75 hover:bg-white/10 hover:text-white ${isToday ? 'ring-1 ring-white/30' : ''}`
      }`}
    >
      {label}
    </button>
  )
}
