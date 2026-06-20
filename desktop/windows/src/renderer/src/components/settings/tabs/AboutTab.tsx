import { Bug, Info } from 'lucide-react'
import { SettingRow } from '../SettingRow'
import { StatusTile } from '../StatusTile'

export function AboutTab(): React.JSX.Element {
  const versions = window.electron.process.versions

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
        icon={Bug}
        title="Report an issue"
        subtitle="Use the Omi support or GitHub issue path with these runtime versions when reporting Windows desktop problems."
        keywords="about report issue bug feedback support logs troubleshooting"
      />
    </>
  )
}
