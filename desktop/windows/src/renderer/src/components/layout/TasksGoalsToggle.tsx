import { NavLink } from 'react-router-dom'
import { cn } from '../../lib/utils'

// Segmented switcher that lives in the header of both the Tasks and Goals
// pages. Goals no longer has its own sidebar item — it's reached from the Tasks
// tab via this toggle. Both pages stay mounted in MainViews, so switching here
// is just a route change (instant, state preserved).
const tabs = [
  { label: 'Tasks', to: '/tasks' },
  { label: 'Goals', to: '/goals' }
] as const

export function TasksGoalsToggle(): React.JSX.Element {
  return (
    <div className="inline-flex items-center gap-1 rounded-2xl border border-white/10 bg-black/20 p-1">
      {tabs.map(({ label, to }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            cn(
              'rounded-xl px-4 py-1.5 font-display text-base font-bold tracking-tight transition-all duration-200',
              isActive ? 'bg-white/15 text-white' : 'text-white/45 hover:bg-white/5 hover:text-white/80'
            )
          }
        >
          {label}
        </NavLink>
      ))}
    </div>
  )
}
