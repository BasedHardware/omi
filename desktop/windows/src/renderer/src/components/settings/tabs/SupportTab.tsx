import { useState } from 'react'
import { Globe, BookOpen, Bug, FileText, Info, Download, CheckCircle, AlertCircle, Loader } from 'lucide-react'
import omiLogo from '../../../assets/omilogo.png'
import { SettingRow } from '../SettingRow'

declare const __APP_VERSION__: string

const { electron, node } = window.electron.process.versions

function openLink(url: string): void {
  window.open(url)
}

type UpdateState =
  | { status: 'idle' }
  | { status: 'checking' }
  | { status: 'up-to-date'; version: string }
  | { status: 'available'; version: string; url: string }
  | { status: 'error'; message: string }

async function checkGithubRelease(): Promise<UpdateState> {
  const res = await fetch(
    'https://api.github.com/repos/BasedHardware/omi/releases/latest',
    { headers: { Accept: 'application/vnd.github.v3+json' } }
  )
  if (!res.ok) throw new Error(`GitHub API ${res.status}`)
  const data = (await res.json()) as { tag_name: string; html_url: string }
  const remote = data.tag_name.replace(/^v/, '').replace(/-windows$/, '')
  const current = __APP_VERSION__
  return remote === current
    ? { status: 'up-to-date', version: current }
    : { status: 'available', version: remote, url: data.html_url }
}

export function SupportTab(): React.JSX.Element {
  const [updateState, setUpdateState] = useState<UpdateState>({ status: 'idle' })

  const handleCheckUpdates = (): void => {
    setUpdateState({ status: 'checking' })
    checkGithubRelease()
      .then(setUpdateState)
      .catch((e: unknown) =>
        setUpdateState({ status: 'error', message: (e as Error).message ?? 'Unknown error' })
      )
  }

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
        icon={Download}
        title="Check for Updates"
        subtitle={
          updateState.status === 'idle'
            ? `Current version: ${__APP_VERSION__}.`
            : updateState.status === 'checking'
              ? 'Checking GitHub for the latest release…'
              : updateState.status === 'up-to-date'
                ? `You're on the latest version (${updateState.version}).`
                : updateState.status === 'available'
                  ? `Version ${updateState.version} is available — open GitHub to download.`
                  : `Could not check for updates: ${updateState.message}`
        }
        keywords="update check releases version latest upgrade"
        control={
          <div className="flex items-center gap-2">
            {updateState.status === 'checking' && (
              <Loader className="h-4 w-4 animate-spin text-text-quaternary" />
            )}
            {updateState.status === 'up-to-date' && (
              <CheckCircle className="h-4 w-4 text-green-400" />
            )}
            {updateState.status === 'error' && (
              <AlertCircle className="h-4 w-4 text-orange-400" />
            )}
            {updateState.status === 'available' ? (
              <button
                onClick={() => openLink(updateState.url)}
                className="btn-ghost text-blue-400"
              >
                Download
              </button>
            ) : (
              <button
                onClick={
                  updateState.status === 'checking' ? undefined : handleCheckUpdates
                }
                disabled={updateState.status === 'checking'}
                className="btn-ghost disabled:opacity-50"
              >
                {updateState.status === 'idle' ? 'Check' : 'Recheck'}
              </button>
            )}
          </div>
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
