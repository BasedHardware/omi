import { useEffect, useRef, useState } from 'react'
import { StepScaffold } from './StepScaffold'
import { ConnectorBrandMark } from '../home/hub/connections/ConnectorBrandMark'
import { useMemories } from '../../hooks/useMemories'
import { useGoogleConnection } from '../../hooks/useGoogleConnection'
import { auth } from '../../lib/firebase'
import { toast } from '../../lib/toast'
import { toastImportTally } from '../../lib/importToast'
import {
  extractPasteMemories,
  importPasteMemories,
  toastForExtractResult
} from '../../lib/pasteImport'
import type { MemorySource } from '../../lib/memoryExtract'
import {
  getCalendarStatus,
  getCalendarOAuthUrl,
  disconnectCalendar,
  pollUntilConnected,
  type CalendarStatus
} from '../../lib/calendarConnect'
import { getImportedCounts, setImportedCount } from '../../lib/onboardingImportCounts'

// Onboarding "Data sources" step — the Windows port of macOS's
// OnboardingDataSourcesStepView. A curated, fixed-order list (NOT the connectors
// marketplace) letting the user seed their second brain with more context before
// finishing: Calendar + Email over the existing OAuth connectors, the already-run
// local-file index, and paste-import of a ChatGPT / Claude memory log.
//
// Windows diverges from Mac in ONE deliberate way: Mac auto-runs background
// readers and gates Continue on a "scanning…" wait. Windows connects over
// user-initiated OAuth (nothing to auto-scan), so there is no fake wait — Continue
// is always available and Skip is always offered. Nothing here is required.

type DataSourcesStepProps = {
  stepIndex: number
  totalSteps: number
  onContinue: () => void
  onSkip: () => void
}

export function DataSourcesStep({
  stepIndex,
  totalSteps,
  onContinue,
  onSkip
}: DataSourcesStepProps): React.JSX.Element {
  return (
    <StepScaffold
      stepIndex={stepIndex}
      totalSteps={totalSteps}
      align="left"
      widthClassName="w-full max-w-[440px]"
      eyebrow="DATA SOURCES"
      title="Your 2nd brain is live."
      subtitle="Connect more of your context — or skip and add it later."
      onContinue={onContinue}
      onSkip={onSkip}
    >
      <div className="w-full divide-y divide-white/5 overflow-hidden rounded-2xl border border-white/5 bg-white/[0.03]">
        <CalendarRow />
        <EmailRow />
        <LocalFilesRow />
        <MemoryLogRow source="chatgpt" />
        <MemoryLogRow source="claude" />
      </div>
    </StepScaffold>
  )
}

// --- Row primitives ---------------------------------------------------------

function BrandChip({
  brand
}: {
  brand: React.ComponentProps<typeof ConnectorBrandMark>['brand']
}): React.JSX.Element {
  return (
    <span className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[9px] border border-white/[0.06] bg-white/[0.05] p-1.5">
      <ConnectorBrandMark brand={brand} />
    </span>
  )
}

function Pill({
  tone = 'primary',
  children,
  ...rest
}: {
  tone?: 'primary' | 'neutral' | 'ghost'
} & React.ButtonHTMLAttributes<HTMLButtonElement>): React.JSX.Element {
  const cls =
    tone === 'primary'
      ? 'bg-white text-black hover:opacity-90'
      : tone === 'neutral'
        ? 'bg-white/[0.08] text-white/85 hover:bg-white/[0.12]'
        : 'text-white/45 hover:text-white/70'
  return (
    <button
      type="button"
      className={
        'rounded-full px-4 py-1.5 text-[13px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ' +
        cls
      }
      {...rest}
    >
      {children}
    </button>
  )
}

function Row({
  brand,
  title,
  status,
  statusTone = 'muted',
  action,
  children
}: {
  brand: React.ComponentProps<typeof ConnectorBrandMark>['brand']
  title: string
  status: React.ReactNode
  statusTone?: 'muted' | 'warn'
  action?: React.ReactNode
  children?: React.ReactNode
}): React.JSX.Element {
  return (
    <div data-testid={`datasource-${brand}`}>
      <div className="flex items-center gap-3 px-4 py-3.5">
        <BrandChip brand={brand} />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-white/90">{title}</div>
          <div
            className={
              'mt-0.5 line-clamp-1 text-xs ' +
              (statusTone === 'warn' ? 'text-amber-300/80' : 'text-white/45')
            }
          >
            {status}
          </div>
        </div>
        {action && <div className="flex shrink-0 items-center gap-1.5">{action}</div>}
      </div>
      {children}
    </div>
  )
}

// --- Calendar (backend-mediated OAuth, reused from lib/calendarConnect) ------

const POLL_INTERVAL_MS = 2000
const POLL_MAX_ATTEMPTS = 60

function CalendarRow(): React.JSX.Element {
  const [status, setStatus] = useState<CalendarStatus>({ connected: false })
  const [connecting, setConnecting] = useState(false)
  const [busy, setBusy] = useState(false)
  const canceled = useRef(false)

  useEffect(() => {
    canceled.current = false
    getCalendarStatus()
      .then((s) => !canceled.current && setStatus(s))
      .catch(() => {})
    return () => {
      canceled.current = true
    }
  }, [])

  const connect = async (): Promise<void> => {
    if (connecting || busy) return
    setConnecting(true)
    try {
      const url = await getCalendarOAuthUrl()
      await window.omi.openExternalUrl(url)
      const ok = await pollUntilConnected(getCalendarStatus, {
        intervalMs: POLL_INTERVAL_MS,
        maxAttempts: POLL_MAX_ATTEMPTS,
        canceled: () => canceled.current
      })
      if (canceled.current) return
      if (ok) {
        setStatus(await getCalendarStatus())
        toast('Google Calendar connected', { tone: 'success' })
      } else {
        toast('Still waiting for Google Calendar', {
          tone: 'warn',
          body: 'Finish the sign-in in your browser, then reopen this step to check.'
        })
      }
    } catch (e) {
      if (!canceled.current)
        toast('Could not start Calendar sign-in', { tone: 'error', body: (e as Error).message })
    } finally {
      if (!canceled.current) setConnecting(false)
    }
  }

  const disconnect = async (): Promise<void> => {
    if (busy) return
    setBusy(true)
    try {
      await disconnectCalendar()
      setStatus({ connected: false })
      toast('Google Calendar disconnected', { tone: 'success' })
    } catch (e) {
      toast('Could not disconnect', { tone: 'error', body: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Row
      brand="calendar"
      title="Calendar"
      status={status.connected ? 'Connected' : 'Import events and recurring routines.'}
      action={
        status.connected ? (
          <Pill tone="ghost" onClick={disconnect} disabled={busy}>
            Disconnect
          </Pill>
        ) : (
          <Pill tone="primary" onClick={connect} disabled={connecting}>
            {connecting ? 'Waiting…' : 'Connect'}
          </Pill>
        )
      }
    />
  )
}

// --- Email / Gmail (client-side loopback OAuth, reused from useGoogleConnection) --

function EmailRow(): React.JSX.Element {
  const { googleEnabled, status, connect, disconnect, busy } = useGoogleConnection()

  if (!googleEnabled) {
    return (
      <Row
        brand="gmail"
        title="Email"
        status="Import email history and follow-ups."
        action={<span className="text-xs text-white/40">Requires setup</span>}
      />
    )
  }

  return (
    <Row
      brand="gmail"
      title="Email"
      status={
        status.connected
          ? status.email
            ? `Connected as ${status.email}`
            : 'Connected'
          : 'Import email history and follow-ups.'
      }
      action={
        status.connected ? (
          <Pill tone="ghost" onClick={disconnect} disabled={busy}>
            Disconnect
          </Pill>
        ) : (
          <Pill tone="primary" onClick={connect} disabled={busy}>
            {busy ? 'Connecting…' : 'Connect'}
          </Pill>
        )
      }
    />
  )
}

// --- Local files (already indexed in the earlier BuildProfile step) ---------

function LocalFilesRow(): React.JSX.Element {
  // The file index runs in the MAIN process during the earlier discovery step and
  // persists; we only READ its status here (never re-scan) and surface the count.
  const [fileCount, setFileCount] = useState<number | null>(null)

  useEffect(() => {
    let alive = true
    window.omi
      .indexFilesStatus()
      .then((s) => alive && setFileCount(s.filesIndexed))
      .catch(() => alive && setFileCount(null))
    return () => {
      alive = false
    }
  }, [])

  const status =
    fileCount && fileCount > 0
      ? `On · ${fileCount.toLocaleString()} file${fileCount === 1 ? '' : 's'} indexed`
      : 'On · indexed on this device'

  return (
    <Row
      brand="omi"
      title="Local files"
      status={status}
      action={<span className="text-xs font-medium text-white/40">On</span>}
    />
  )
}

// --- ChatGPT / Claude memory-log paste import -------------------------------

const MEMORY_LOG_PROMPT =
  "Return everything you know about me inside one fenced code block. Include long-term memory, bio details, and any model-set context you have with dates when available. I want a thorough memory export of what you've learned about me. Skip tool details and include only information that is actually about me. Be exhaustive and careful."

const SOURCE_TITLE: Record<MemorySource, string> = {
  chatgpt: 'ChatGPT',
  claude: 'Claude'
}

// Prefilled deep links (mirrors Mac's prefilledBrowserURL): ChatGPT takes the
// prompt on the root `?q=`, Claude on `/new?q=`.
function prefilledUrl(source: MemorySource): string {
  const q = encodeURIComponent(MEMORY_LOG_PROMPT)
  return source === 'chatgpt' ? `https://chatgpt.com/?q=${q}` : `https://claude.ai/new?q=${q}`
}

function MemoryLogRow({ source }: { source: MemorySource }): React.JSX.Element {
  const { memories, refresh } = useMemories()
  const uid = auth.currentUser?.uid ?? null
  // Cross-account-guarded: a different signed-in user never inherits this tally.
  const [importedCount, setImportedCountState] = useState(() => getImportedCounts(uid)[source])
  const [open, setOpen] = useState(false)
  const [dump, setDump] = useState('')
  const [importing, setImporting] = useState(false)

  const title = SOURCE_TITLE[source]
  const connected = importedCount > 0

  const openAndCopyPrompt = async (): Promise<void> => {
    // Belt-and-suspenders like Mac: open the provider with the prompt prefilled AND
    // put the prompt on the clipboard, so the user can paste it either way.
    try {
      await navigator.clipboard.writeText(MEMORY_LOG_PROMPT)
    } catch {
      /* clipboard may be unavailable; the prefilled URL still carries the prompt */
    }
    try {
      await window.omi.openExternalUrl(prefilledUrl(source))
    } catch (e) {
      toast(`Could not open ${title}`, { tone: 'error', body: (e as Error).message })
      return
    }
    toast(`Prompt copied — paste it in ${title}`, { tone: 'success' })
  }

  const runImport = async (): Promise<void> => {
    if (!dump.trim() || importing) return
    setImporting(true)
    try {
      const r = await extractPasteMemories(
        dump,
        source,
        memories.map((m) => m.content)
      )
      toastForExtractResult(r)
      if (r.memories.length === 0) return
      const tally = await importPasteMemories(r.memories)
      toastImportTally(tally)
      if (tally.ok > 0) {
        setImportedCount(uid, source, tally.ok)
        setImportedCountState(tally.ok)
        await refresh()
        setDump('')
        setOpen(false)
      }
    } catch (e) {
      toast('Could not import memories', { tone: 'error', body: (e as Error).message })
    } finally {
      setImporting(false)
    }
  }

  return (
    <Row
      brand={source}
      title={title}
      status={
        connected
          ? `${importedCount.toLocaleString()} memor${importedCount === 1 ? 'y' : 'ies'} imported`
          : 'Paste your memory export.'
      }
      action={
        connected ? (
          <span className="text-xs font-medium text-white/40">Imported</span>
        ) : (
          <Pill tone={open ? 'ghost' : 'primary'} onClick={() => setOpen((v) => !v)}>
            {open ? 'Close' : 'Connect'}
          </Pill>
        )
      }
    >
      {open && !connected && (
        <div className="space-y-3 px-4 pb-4">
          <p className="text-xs leading-relaxed text-white/50">
            Open {title}, paste the copied prompt, then drop the full response here.
          </p>
          <Pill tone="neutral" onClick={openAndCopyPrompt}>
            Open {title} &amp; Copy Prompt
          </Pill>
          <textarea
            value={dump}
            onChange={(e) => setDump(e.target.value)}
            rows={4}
            placeholder={`Paste ${title}’s full response here…`}
            className="w-full resize-none rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5 text-[13px] text-white/85 placeholder:text-white/30 focus:border-white/20 focus:outline-none"
          />
          <div className="flex items-center gap-2">
            {/* The white/primary commit only appears once there's text to import —
                so it never sits next to Connect as a dimmed charcoal button (which
                muddied the button hierarchy). Matches the Hub PasteImportConnector's
                progressive reveal. "Open & Copy Prompt" stays the secondary CTA. */}
            {dump.trim() && (
              <Pill tone="primary" onClick={runImport} disabled={importing}>
                {importing ? 'Importing…' : `Import ${title}`}
              </Pill>
            )}
            <Pill
              tone="ghost"
              onClick={() => {
                setDump('')
                setOpen(false)
              }}
            >
              Cancel
            </Pill>
          </div>
        </div>
      )}
    </Row>
  )
}
