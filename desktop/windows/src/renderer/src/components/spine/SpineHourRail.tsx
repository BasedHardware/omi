// The 24-hour density rail beside a day. The maths lives in spineRailModel.ts.

import { formatHourLabel } from '../../lib/spine/spineModel'
import {
  HOT_THRESHOLD,
  LABELLED_HOURS,
  RENDERED_HOURS,
  hourDensity,
  railFooter,
  railHeadline
} from './spineRailModel'

export function SpineHourRail(props: {
  hourCounts: number[]
  momentCount: number | null
  dayTitle: string
  conversationCount: number
  currentHour: number | null
}): React.JSX.Element {
  const density = hourDensity(props.hourCounts)
  const headline = railHeadline(props.momentCount)
  return (
    <aside className="w-[154px] shrink-0 px-3 py-4" aria-label={`${props.dayTitle} activity`}>
      <p className="truncate text-2xl font-semibold text-white/90">{headline.value}</p>
      <p className="text-[11px] text-white/40">{headline.caption}</p>
      <p className="mt-0.5 truncate text-[11px] text-white/30">{props.dayTitle}</p>

      <div className="mt-3 flex flex-col gap-[1px]">
        {RENDERED_HOURS.map((hour) => {
          const weight = density[hour] ?? 0
          const isCurrent = props.currentHour === hour
          const isHot = weight >= HOT_THRESHOLD
          const labelled = LABELLED_HOURS.has(hour) || isCurrent
          return (
            <div key={hour} className="flex h-[7px] items-center gap-1.5">
              <span
                className="block rounded-full bg-white"
                style={{
                  width: `${14 + weight * 78}px`,
                  height: isCurrent ? 6 : 5,
                  opacity: isCurrent ? 0.85 : isHot ? 0.42 : 0.2
                }}
              />
              {labelled && (
                <span
                  className={`text-[9px] tabular-nums ${
                    isCurrent ? 'font-semibold text-white/60' : 'text-white/25'
                  }`}
                >
                  {formatHourLabel(hour)}
                </span>
              )}
            </div>
          )
        })}
      </div>

      {railFooter(props.conversationCount) !== null && (
        <p className="mt-3 text-[11px] text-white/30">{railFooter(props.conversationCount)}</p>
      )}
    </aside>
  )
}
