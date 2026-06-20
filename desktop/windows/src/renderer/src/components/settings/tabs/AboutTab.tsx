import { useEffect, useState } from 'react'
import { ExternalLink, RefreshCw, Heart } from 'lucide-react'

export function AboutTab(): React.JSX.Element {
  const [version, setVersion] = useState<string>('1.0.0')
  const [checkingUpdate, setCheckingUpdate] = useState(false)
  const [updateStatus, setUpdateStatus] = useState<string | null>(null)

  useEffect(() => {
    window.omi.getAppVersion?.().then(setVersion).catch(() => {})
  }, [])

  const checkForUpdates = async (): Promise<void> => {
    setCheckingUpdate(true)
    setUpdateStatus(null)
    try {
      await window.omi.checkForUpdates?.()
      setUpdateStatus('Omi is up to date.')
    } catch {
      setUpdateStatus('Could not check for updates. Try again later.')
    } finally {
      setCheckingUpdate(false)
    }
  }

  return (
    <div className="space-y-8">
      {/* App info */}
      <div className="flex items-center gap-5">
        <img
          src="https://personas.omi.me/omilogo.png"
          alt="Omi"
          className="h-16 w-16 rounded-2xl"
        />
        <div>
          <h2 className="text-xl font-bold text-text-primary">Omi for Windows</h2>
          <p className="mt-0.5 text-sm text-text-tertiary">Version {version}</p>
          <p className="mt-1 text-xs text-text-quaternary">
            The world's leading open-source AI wearable
          </p>
        </div>
      </div>

      {/* Update check */}
      <div className="rounded-xl border border-white/[0.07] bg-white/[0.03] p-5">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-text-primary">Software update</p>
            <p className="mt-0.5 text-xs text-text-tertiary">
              {updateStatus ?? `You're running version ${version}`}
            </p>
          </div>
          <button
            onClick={() => void checkForUpdates()}
            disabled={checkingUpdate}
            className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.04] px-4 py-2 text-sm text-text-secondary hover:bg-white/[0.08] disabled:opacity-50"
          >
            <RefreshCw className={['h-3.5 w-3.5', checkingUpdate ? 'animate-spin' : ''].join(' ')} />
            {checkingUpdate ? 'Checking…' : 'Check for updates'}
          </button>
        </div>
      </div>

      {/* Links */}
      <div className="space-y-1">
        {[
          { label: 'omi.me — website', href: 'https://omi.me' },
          { label: 'GitHub — open source', href: 'https://github.com/BasedHardware/omi' },
          { label: 'Discord community', href: 'https://discord.gg/omi' },
          { label: 'Privacy policy', href: 'https://omi.me/privacy' },
          { label: 'Terms of service', href: 'https://omi.me/terms' },
        ].map(({ label, href }) => (
          <button
            key={href}
            onClick={() => window.omi.openExternal?.(href)}
            className="flex w-full items-center justify-between rounded-xl px-4 py-3 text-sm text-text-secondary hover:bg-white/[0.04] hover:text-text-primary"
          >
            {label}
            <ExternalLink className="h-3.5 w-3.5 text-text-quaternary" />
          </button>
        ))}
      </div>

      {/* Made with love */}
      <p className="flex items-center justify-center gap-1.5 pt-2 text-xs text-text-quaternary">
        Made with <Heart className="h-3 w-3 text-red-400" /> by the Omi team
      </p>
    </div>
  )
}
