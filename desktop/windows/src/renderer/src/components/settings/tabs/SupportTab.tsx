import { Globe, BookOpen, Bug, FileText, Info } from 'lucide-react'
import omiLogo from '../../../assets/omilogo.png'
import { SettingRow } from '../SettingRow'

declare const __APP_VERSION__: string

const { electron, node } = window.electron.process.versions

function openLink(url: string): void {
  window.open(url)
}

export function SupportTab(): React.JSX.Element {
  return (
    <>
      <div className="mb-6 flex items-center gap-4 rounded-xl border border-white/[0.08] bg-white/[0.04] px-5 py-4">
        <img src={omiLogo} alt="omi" className="h-12 w-12 shrink-0 rounded-2xl" />
        <div className="min-w-0 flex-1">
          <p className="text-[18px] font-bold text-text-primary">omi</p>
          <p className="mt-0.5 text-sm text-text-tertiary">Version {__APP_VERSION__} for Windows</p>
          <p className="text-xs text-text-tertiary opacity-60">
            Electron {electron} · Node {node}
          </p>
        </div>
      </div>

      <SettingRow
        icon={Globe}
        title="Visit Website"
        subtitle="omi.me — your personal AI memory companion"
        keywords="website home omi.me"
        control={
          <button onClick={() => openLink('https://omi.me')} className="btn-ghost">
            Open
          </button>
        }
      />
      <SettingRow
        icon={BookOpen}
        title="Help & Docs"
        subtitle="Guides, API reference, and troubleshooting"
        keywords="docs help guide documentation api reference"
        control={
          <button onClick={() => openLink('https://help.omi.me')} className="btn-ghost">
            Open
          </button>
        }
      />
      <SettingRow
        icon={Bug}
        title="Report an Issue"
        subtitle="Open a GitHub issue to report a bug or request a feature"
        keywords="bug report issue github feedback problem"
        control={
          <button
            onClick={() => openLink('https://github.com/BasedHardware/omi/issues')}
            className="btn-ghost"
          >
            GitHub
          </button>
        }
      />
      <SettingRow
        icon={FileText}
        title="Privacy Policy"
        subtitle="How omi handles and stores your data"
        keywords="privacy data policy tracking"
        control={
          <button onClick={() => openLink('https://www.omi.me/privacy')} className="btn-ghost">
            Open
          </button>
        }
      />
      <SettingRow
        icon={Info}
        title="Terms of Service"
        subtitle="Usage terms and conditions"
        keywords="terms conditions tos legal"
        control={
          <button onClick={() => openLink('https://www.omi.me/terms')} className="btn-ghost">
            Open
          </button>
        }
      />
      <SettingRow
        title="Local data"
        subtitle="Screen frames, transcripts, and your knowledge graph are stored on this machine only. Cloud conversations and memories sync to omi's encrypted servers per your privacy settings."
        keywords="data local storage privacy encryption on device"
      />
    </>
  )
}
