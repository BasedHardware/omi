import type { BeeperStatus } from '../../../../shared/types'

/** Token paste + Install Beeper. Shared by onboarding and the Connect hub. */
export function BeeperConnectForm({
  status,
  token,
  busy,
  error,
  onToken,
  onConnect,
  onInstall
}: {
  status: BeeperStatus
  token: string
  busy: boolean
  error: string | null
  onToken: (v: string) => void
  onConnect: () => void
  onInstall: () => void
}): React.JSX.Element {
  if (status.connected) {
    const names = status.accounts.filter((a) => a.connected).map((a) => a.network)
    return (
      <p className="text-[13px] text-white/70">
        {names.length > 0
          ? `Connected · ${names.join(', ')}`
          : 'Connected. Link WhatsApp or Telegram inside Beeper.'}
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-[12px] leading-relaxed text-white/45">
        {status.running
          ? 'Beeper is running. In Beeper, open Settings → Integrations → Approved connections → +, then paste the token.'
          : 'Install Beeper, connect WhatsApp or Telegram, then paste an access token here.'}
      </p>
      {!status.running && (
        <button
          type="button"
          onClick={onInstall}
          className="self-start rounded-full bg-white px-4 py-1.5 text-[13px] font-medium text-black hover:opacity-90"
        >
          Install Beeper
        </button>
      )}
      <div className="flex gap-2">
        <input
          type="password"
          autoComplete="off"
          placeholder="Paste access token"
          value={token}
          onChange={(e) => onToken(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') onConnect()
          }}
          className="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-[13px] text-white placeholder:text-white/30 outline-none focus:border-white/25"
        />
        <button
          type="button"
          onClick={onConnect}
          disabled={busy || !token.trim()}
          className="rounded-lg bg-white px-3 py-2 text-[13px] font-medium text-black disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? 'Connecting…' : 'Connect'}
        </button>
      </div>
      {error && <p className="text-[12px] text-red-300/90">{error}</p>}
    </div>
  )
}
