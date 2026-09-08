import { useEffect, useState } from 'react'
import { getPreferences, onPreferencesChange } from '../lib/preferences'
import { LegacyHome } from './LegacyHome'
import { HomeHub } from '../components/home/hub/HomeHub'

// Home is a switch, not a screen. The Hub (the macOS DashboardPage port) is the
// default; `useLegacyHomeDesign` puts the original screen back. The subscription
// keeps the switch live, so flipping the toggle in Settings swaps the screen
// without a restart.
//
// App-lifetime background engines (knowledge graph, screen synthesis, insights,
// retention) deliberately do NOT live here — they run from the app shell (App.tsx),
// so neither design owns them and neither can silently switch them off.
export function Home(): React.JSX.Element {
  const [legacy, setLegacy] = useState<boolean>(() => getPreferences().useLegacyHomeDesign ?? false)
  useEffect(() => onPreferencesChange((p) => setLegacy(p.useLegacyHomeDesign ?? false)), [])

  return legacy ? <LegacyHome /> : <HomeHub />
}
