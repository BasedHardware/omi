import { useEffect, useState } from 'react'
import { Bug, Info, Newspaper } from 'lucide-react'
import type { WindowsUpdateStatus } from '../../../../../shared/types'
import { SettingRow } from '../SettingRow'
import { StatusTile } from '../StatusTile'

export function AboutTab(): React.JSX.Element {
  const versions = window.electron.process.versions
  const [updates, setUpdates] = useState<WindowsUpdateStatus | null>(null)

  useEffect(() => {
    void window.omi.updaterGetStatus().then(setUpdates)
  }, [])

  return (
    <>
      <SettingRow
        icon={Info}
        title="Version information"
        subtitle="Runtime versions for this Windows desktop build."
        keywords="about version build electron chromium chrome node app information"
      >
        <div className="grid gap-2 sm:grid-cols-3">
          <StatusTile label="Electron" value={versions.electron ?? 'Unknown'} />
          <StatusTile label="Chromium" value={versions.chrome ?? 'Unknown'} />
          <StatusTile label="Node" value={versions.node ?? 'Unknown'} />
        </div>
      </SettingRow>
      <SettingRow
        icon={Newspaper}
        title="What's New"
        subtitle="Open release notes and see the Windows updater feed state."
        keywords="about what's new whats new changelog release notes update updater"
        control={
          <button
            onClick={() => void window.omi.systemOpenExternal('releaseNotes')}
            className="btn-ghost px-3 py-2"
          >
            Open
          </button>
        }
      >
        <div className="grid gap-2 sm:grid-cols-3">
          <StatusTile
            label="Updates"
            value={!updates ? 'Checking' : updates.enabled ? 'Enabled' : 'Disabled'}
            tone={updates?.enabled ? 'good' : 'neutral'}
          />
          <StatusTile
            label="Feed"
            value={!updates ? 'Checking' : updates.configured ? 'Configured' : 'Missing'}
            tone={updates?.configured ? 'good' : 'warn'}
          />
          <StatusTile
            label="Last event"
            value={updates?.lastEvent ?? 'None'}
            tone={updates?.lastError ? 'warn' : 'neutral'}
          />
        </div>
      </SettingRow>
      <SettingRow
        icon={Bug}
        title="Report an issue"
        subtitle="Use the Omi support or GitHub issue path with these runtime versions when reporting Windows desktop problems."
        keywords="about report issue bug feedback support logs troubleshooting"
      />
    </>
  )
}
