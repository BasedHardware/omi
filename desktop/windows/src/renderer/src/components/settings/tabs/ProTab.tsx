import { useEffect, useState } from 'react'
import { Sparkles, KeyRound, CloudUpload, RefreshCw, Clock } from 'lucide-react'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'
import {
  getTier,
  proActive,
  daysLeftInTrial,
  canTrial,
  startTrial,
  redeemProKey,
  onLicenseChange
} from '../../../lib/license'
import { PRO_FEATURES } from '../../../../../shared/license'
import { getSyncState, setSyncEnabled, runSync } from '../../../lib/cloudSync'

const WAITLIST_URL = 'https://cortex.apym.io'

export function ProTab(): React.JSX.Element {
  const [tier, setTier] = useState(getTier())
  const [keyInput, setKeyInput] = useState('')
  const [keyError, setKeyError] = useState('')
  const [sync, setSync] = useState(getSyncState())
  const [syncMsg, setSyncMsg] = useState('')

  useEffect(() => onLicenseChange(() => setTier(getTier())), [])

  const isPro = proActive()

  return (
    <>
      <SettingRow
        icon={Sparkles}
        title="Your plan"
        subtitle={
          tier === 'pro'
            ? 'Cortex Pro — thanks for supporting Cortex.'
            : tier === 'trial'
              ? `Cortex Pro trial — ${daysLeftInTrial()} day(s) remaining.`
              : 'Cortex Free — open source, fully functional.'
        }
        keywords="plan tier pro free trial upgrade subscription"
        control={
          <span
            className="badge"
            style={isPro ? { color: 'var(--accent)', borderColor: 'var(--accent)' } : undefined}
          >
            {tier === 'pro' ? 'PRO' : tier === 'trial' ? 'TRIAL' : 'FREE'}
          </span>
        }
      />

      {!isPro && canTrial() && (
        <SettingRow
          icon={Clock}
          title="Start your 14-day Pro trial"
          subtitle="Try every Pro feature free for 14 days. No card required."
          keywords="trial free try pro"
          control={
            <button
              className="btn-primary"
              onClick={() => {
                startTrial()
                setTier(getTier())
              }}
            >
              Start trial
            </button>
          }
        />
      )}

      {!isPro && (
        <SettingRow
          icon={Sparkles}
          title="Join the waitlist"
          subtitle="Cortex Pro is rolling out. Reserve your spot at cortex.apym.io."
          keywords="waitlist join pro upgrade buy"
          control={
            <a className="btn-primary" href={WAITLIST_URL} target="_blank" rel="noreferrer">
              Join waitlist
            </a>
          }
        />
      )}

      <SettingRow
        icon={KeyRound}
        title="Redeem a Pro key"
        subtitle="Already have a Cortex Pro key? Enter it here."
        keywords="redeem license key activate pro"
      >
        <div className="mt-2 flex gap-2">
          <input
            className="input-field"
            placeholder="CORTEX-PRO-XXXX-XXXX-XXXX"
            value={keyInput}
            onChange={(e) => {
              setKeyInput(e.target.value)
              setKeyError('')
            }}
          />
          <button
            className="btn-primary shrink-0"
            onClick={() => {
              if (redeemProKey(keyInput)) {
                setTier(getTier())
                setKeyInput('')
              } else {
                setKeyError('That key doesn’t look valid.')
              }
            }}
          >
            Redeem
          </button>
        </div>
        {keyError && <div className="mt-2 text-sm text-amber-400">{keyError}</div>}
      </SettingRow>

      {/* Pro features overview */}
      {PRO_FEATURES.map((f) => (
        <SettingRow
          key={f.id}
          icon={Sparkles}
          title={f.label}
          subtitle={f.description}
          dot={isPro ? 'on' : 'off'}
          keywords={`pro feature ${f.id}`}
        />
      ))}

      {/* Cloud sync — Pro-gated */}
      <SettingRow
        icon={CloudUpload}
        title="Cloud sync"
        subtitle={
          isPro
            ? 'Sync conversations, memories and settings across devices.'
            : 'Available on Cortex Pro. Start a trial or redeem a key to enable.'
        }
        keywords="cloud sync backup devices pro"
        control={
          <Toggle
            on={sync.enabled && isPro}
            disabled={!isPro}
            onChange={(v) => {
              setSyncEnabled(v)
              setSync(getSyncState())
            }}
          />
        }
      >
        {isPro && sync.enabled && (
          <div className="mt-3 flex items-center gap-3">
            <button
              className="btn-ghost"
              onClick={async () => {
                setSyncMsg('Syncing…')
                const r = await runSync()
                setSync(getSyncState())
                setSyncMsg(r.reason ?? (r.ok ? 'Synced.' : 'Sync failed.'))
              }}
            >
              <RefreshCw className="h-4 w-4" /> Sync now
            </button>
            <span className="text-sm text-text-tertiary">
              {syncMsg ||
                (sync.lastSyncedAt
                  ? `Last synced ${new Date(sync.lastSyncedAt).toLocaleString()}`
                  : 'Never synced')}
            </span>
          </div>
        )}
      </SettingRow>
    </>
  )
}
