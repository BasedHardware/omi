import { useGoogleConnection } from '../../../../hooks/useGoogleConnection'
import { ConnectorRow, PillButton } from './ConnectorRow'
import { ConnectorBrandMark } from './ConnectorBrandMark'

// Email (Gmail) via the CLIENT-SIDE loopback OAuth lane — turns recent email
// subjects/senders into memories. Config-gated on shipped builds (needs a Google
// client id compiled into main), so when unavailable the row stays a single-line,
// non-dead "requires setup" state. Calendar is a separate card (CalendarConnector).
// All logic — status, connect/disconnect/sync, and the background auto-resync — is
// shared with Settings via useGoogleConnection.

export function GmailConnector(): React.JSX.Element {
  const { googleEnabled, status, connect, disconnect, syncNow, busy, syncing } =
    useGoogleConnection()

  if (!googleEnabled) {
    return (
      <ConnectorRow
        iconNode={<ConnectorBrandMark brand="gmail" />}
        title="Email"
        description="Import email history and follow-ups."
        action={<span className="text-[12px] text-home-faint">Requires setup</span>}
      />
    )
  }

  const description = status.connected
    ? status.email
      ? `Connected as ${status.email}`
      : 'Connected'
    : 'Import email history and follow-ups.'

  return (
    <ConnectorRow
      iconNode={<ConnectorBrandMark brand="gmail" />}
      title="Email"
      description={description}
      action={
        status.connected ? (
          <>
            <PillButton tone="neutral" onClick={syncNow} disabled={syncing}>
              {syncing ? 'Syncing…' : 'Sync now'}
            </PillButton>
            <PillButton tone="ghost" onClick={disconnect} disabled={busy}>
              Disconnect
            </PillButton>
          </>
        ) : (
          <PillButton tone="primary" onClick={connect} disabled={busy}>
            {busy ? 'Connecting…' : 'Connect'}
          </PillButton>
        )
      }
    />
  )
}
