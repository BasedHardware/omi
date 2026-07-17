// About settings tab. Mac reference: SettingsContentView+Controls.swift (About +
// Software Updates).
//
// Windows machinery used:
//  - window.omi.getAppVersion — Electron app name + version.
//  - External links via <a target="_blank"> (main routes http/https to the OS
//    browser through setWindowOpenHandler → shell.openExternal).
//  - Release notes via the existing whatsNewOpenNotes IPC (GitHub releases).
//  - Software updates: window.omi.checkForUpdates (electron-updater; inert in
//    unpackaged dev → "unsupported") and the staged-update restart affordance
//    (getPendingUpdate + onUpdateReady + quitApp), relocated here from General.
//
// Privacy Policy is intentionally not a link here: Omi's privacy content lives in
// the dedicated Privacy tab, and there is no confirmed standalone public URL to
// link without guessing.
import { useEffect, useState } from 'react'
import {
  Info,
  Globe,
  LifeBuoy,
  FileText,
  Newspaper,
  RefreshCw,
  Download,
  FlaskConical,
  ExternalLink,
  ChevronRight
} from 'lucide-react'
import type { UpdateCheckResult } from '../../../../../shared/types'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'

type Link = { label: string; icon: typeof Globe } & ({ href: string } | { onClick: () => void })

const LINKS: Link[] = [
  { label: 'Visit website', icon: Globe, href: 'https://omi.me' },
  { label: 'Help center', icon: LifeBuoy, href: 'https://help.omi.me' },
  { label: 'Terms of service', icon: FileText, href: 'https://omi.me/terms' },
  { label: 'Release notes', icon: Newspaper, onClick: () => window.omi?.whatsNewOpenNotes?.() }
]

function checkResultMessage(r: UpdateCheckResult): string {
  switch (r.status) {
    case 'unsupported':
      return `Updates install automatically. You're on version ${r.version ?? 'this build'}.`
    case 'up-to-date':
      return `You're on the latest version (${r.version ?? 'current'}).`
    case 'update-available':
      return `Update available${r.version ? ` (version ${r.version})` : ''} — it will install the next time you restart Omi.`
    case 'error':
      return `Couldn't check for updates${r.message ? `: ${r.message}` : '.'}`
    default:
      return ''
  }
}

export function AboutTab(): React.JSX.Element {
  const [version, setVersion] = useState<string | null>(null)
  const [name, setName] = useState<string | null>(null)
  const [pending, setPending] = useState<string | null>(null)
  const [checking, setChecking] = useState(false)
  const [checkMsg, setCheckMsg] = useState<string | null>(null)
  const [beta, setBeta] = useState<boolean | null>(null)

  useEffect(() => {
    void window.omi?.getAppVersion?.().then((v) => {
      if (!v) return
      setVersion(v.version)
      setName(v.name)
    })
    // The one-shot update:ready event usually fires while Settings is unmounted —
    // query the staged update on mount, and also subscribe for the live case.
    void window.omi?.getPendingUpdate?.().then((p) => {
      if (p?.version) setPending(p.version)
    })
    void window.omi?.getBetaUpdatesOptIn?.().then((v) => setBeta(!!v))
    return window.omi?.onUpdateReady?.((info) => setPending(info.version))
  }, [])

  const checkForUpdates = async (): Promise<void> => {
    setChecking(true)
    setCheckMsg(null)
    try {
      const res = await window.omi?.checkForUpdates?.()
      if (res) {
        setCheckMsg(checkResultMessage(res))
        if (res.status === 'update-available' && res.version) setPending(res.version)
      }
    } finally {
      setChecking(false)
    }
  }

  // Opt in/out of pre-release (beta) builds. The pref is persisted in main and the
  // updater flips its channel + re-checks live; opting IN also kicks a UI check so
  // a newer beta shows up here immediately rather than on the next background poll.
  const toggleBeta = async (on: boolean): Promise<void> => {
    setBeta(on)
    const next = await window.omi?.setBetaUpdatesOptIn?.(on)
    if (typeof next === 'boolean') setBeta(next)
    if (on) void checkForUpdates()
  }

  return (
    <>
      <SettingRow
        icon={Info}
        title="Omi for Windows"
        subtitle={
          version
            ? `Version ${version}${name && name.toLowerCase() !== 'omi' ? ` · ${name}` : ''}`
            : 'Loading version…'
        }
        keywords="about version build app info omi"
      />

      <SettingRow
        icon={Globe}
        title="Links"
        subtitle="Learn more about Omi, get help, and read the terms."
        keywords="website help support terms release notes links docs"
      >
        <div className="divide-y divide-white/[0.06] overflow-hidden rounded-xl border border-white/10 bg-white/[0.02]">
          {LINKS.map((l) => {
            const Icon = l.icon
            const isExternal = 'href' in l
            const className =
              'flex w-full items-center gap-3 px-4 py-3 text-sm text-white/85 transition-colors hover:bg-white/[0.05]'
            const inner = (
              <>
                <Icon className="h-4 w-4 shrink-0 text-white/55" strokeWidth={1.75} />
                <span className="flex-1 text-left">{l.label}</span>
                {isExternal ? (
                  <ExternalLink className="h-4 w-4 shrink-0 text-white/35" strokeWidth={1.75} />
                ) : (
                  <ChevronRight className="h-4 w-4 shrink-0 text-white/35" strokeWidth={1.75} />
                )}
              </>
            )
            return isExternal ? (
              <a key={l.label} href={l.href} target="_blank" rel="noreferrer" className={className}>
                {inner}
              </a>
            ) : (
              <button key={l.label} type="button" onClick={l.onClick} className={className}>
                {inner}
              </button>
            )
          })}
        </div>
      </SettingRow>

      <SettingRow
        icon={RefreshCw}
        title="Software updates"
        subtitle="Omi updates itself in the background and installs the next time you restart."
        keywords="update upgrade version check for updates release"
        note={checkMsg && <p className="text-xs text-white/60">{checkMsg}</p>}
        control={
          <button
            type="button"
            onClick={() => void checkForUpdates()}
            disabled={checking}
            className="rounded-md border border-white/15 px-3 py-1.5 text-xs text-white transition-colors hover:bg-white/10 disabled:opacity-40"
          >
            {checking ? 'Checking…' : 'Check for updates'}
          </button>
        }
      />

      <SettingRow
        icon={FlaskConical}
        dot={beta ? 'on' : 'off'}
        title="Receive beta updates"
        subtitle="Get pre-release versions early. Beta builds get new features first but may be less stable. Turn off to stay on stable releases."
        keywords="beta prerelease pre-release channel early access insider unstable updates test"
        control={
          <Toggle
            on={!!beta}
            onChange={(on) => void toggleBeta(on)}
            disabled={beta === null}
            label="Receive beta updates"
          />
        }
      />

      {pending && (
        <SettingRow
          icon={Download}
          dot="on"
          title="Update ready"
          subtitle={`Version ${pending} is ready. Restart Omi to apply it.`}
          keywords="update upgrade restart version release ready"
          control={
            <button
              type="button"
              onClick={() => window.omi?.quitApp?.()}
              className="rounded-md bg-white px-3 py-1.5 text-xs font-medium text-black transition-opacity hover:opacity-90"
            >
              Restart to update
            </button>
          }
        />
      )}
    </>
  )
}
