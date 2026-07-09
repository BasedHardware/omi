import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Bot,
  Check,
  Clipboard,
  ExternalLink,
  KeyRound,
  Loader2,
  Server,
  TestTube2
} from 'lucide-react'
import type { McpKeyMetadata } from '../../../../shared/types'
import { fetchFirebaseIdToken } from '../../lib/apiClient'
import { mcpDestinations, type McpDestination } from '../../lib/mcpDestinations'

type CopyState = {
  target: string
  label: string
} | null

const MCP_KEY_PLACEHOLDER = 'YOUR_OMI_MCP_KEY'

function CodeBlock({
  title,
  value,
  copyTarget,
  disabled,
  onCopy
}: {
  title: string
  value: string
  copyTarget: string
  disabled?: boolean
  onCopy: (value: string, label: string) => void
}): React.JSX.Element {
  return (
    <div
      className={`rounded-2xl border border-white/10 bg-black/25 p-3 ${disabled ? 'opacity-55' : ''}`}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase text-white/45">{title}</span>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => onCopy(copyTarget, title)}
            className="rounded-lg p-1.5 text-white/50 transition-colors hover:bg-white/10 hover:text-white disabled:opacity-40"
            title={`Copy ${title}`}
            disabled={disabled}
          >
            <Clipboard className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
      <pre className="max-h-52 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-white/75">
        {value}
      </pre>
    </div>
  )
}

function DestinationButton({
  destination,
  selected,
  onSelect
}: {
  destination: McpDestination
  selected: boolean
  onSelect: () => void
}): React.JSX.Element {
  return (
    <button
      onClick={onSelect}
      className={`flex min-h-[9.5rem] flex-col rounded-2xl border p-4 text-left transition-all duration-200 ${
        selected
          ? 'border-white/25 bg-white/[0.12] text-white shadow-lg shadow-black/20'
          : 'border-white/10 bg-white/[0.04] text-white/75 hover:border-white/18 hover:bg-white/[0.07] hover:text-white'
      }`}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-black/25">
          <Bot className="h-4 w-4" />
        </div>
        {selected && <Check className="h-4 w-4 text-white/70" />}
      </div>
      <div className="font-display text-sm font-semibold">{destination.title}</div>
      <div className="mt-1 text-xs text-white/45">{destination.subtitle}</div>
      <p className="mt-3 line-clamp-3 text-xs leading-relaxed text-white/55">
        {destination.description}
      </p>
    </button>
  )
}

export function McpConnectorSetup({
  onKeyStateChange
}: {
  onKeyStateChange?: (hasKey: boolean) => void
} = {}): React.JSX.Element {
  const [selectedId, setSelectedId] = useState(mcpDestinations[0].id)
  const [storedKey, setStoredKey] = useState<McpKeyMetadata | null>(null)
  const [loadingKey, setLoadingKey] = useState(true)
  const [generating, setGenerating] = useState(false)
  const testRunId = useRef(0)
  const [copyState, setCopyState] = useState<CopyState>(null)
  const [testState, setTestState] = useState<{
    kind: 'idle' | 'running' | 'success' | 'error'
    message: string
  }>({
    kind: 'idle',
    message: ''
  })
  const [keyError, setKeyError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    window.omi
      .mcpKeyRead()
      .then((record) => {
        if (!cancelled) {
          setStoredKey(record)
          onKeyStateChange?.(Boolean(record))
        }
      })
      .catch((error) => {
        if (!cancelled) setKeyError((error as Error).message)
      })
      .finally(() => {
        if (!cancelled) setLoadingKey(false)
      })
    return () => {
      cancelled = true
    }
  }, [onKeyStateChange])

  const selectedDestination = useMemo(
    () =>
      mcpDestinations.find((destination) => destination.id === selectedId) ?? mcpDestinations[0],
    [selectedId]
  )
  const setup = useMemo(() => selectedDestination.setup(MCP_KEY_PLACEHOLDER), [selectedDestination])

  const copy = async (value: string, label: string): Promise<void> => {
    try {
      setKeyError(null)
      if (value === MCP_KEY_PLACEHOLDER) {
        const result = await window.omi.mcpKeyCopy({ kind: 'key' })
        if (!result.copied) return
      } else if (value.includes(MCP_KEY_PLACEHOLDER)) {
        const result = await window.omi.mcpKeyCopy({ kind: 'text', text: value })
        if (!result.copied) return
      } else {
        await navigator.clipboard.writeText(value)
      }
    } catch (error) {
      setKeyError(`Could not copy ${label}: ${(error as Error).message}`)
      return
    }
    setCopyState({ target: value, label })
    window.setTimeout(() => {
      setCopyState((current) => (current?.target === value ? null : current))
    }, 1800)
  }

  const generateKey = async (): Promise<void> => {
    if (generating || testState.kind === 'running') return
    testRunId.current += 1
    setGenerating(true)
    setKeyError(null)
    setTestState({ kind: 'idle', message: '' })
    try {
      // Main creates + stores the key and returns masked metadata only; the raw
      // key never enters this renderer.
      const token = await fetchFirebaseIdToken()
      const metadata = await window.omi.mcpKeyCreateAndStore(token)
      setStoredKey(metadata)
      onKeyStateChange?.(true)
    } catch (error) {
      setKeyError((error as Error).message)
    } finally {
      setGenerating(false)
    }
  }

  const testConnection = async (): Promise<void> => {
    if (!storedKey || testState.kind === 'running') return
    const runId = testRunId.current + 1
    testRunId.current = runId
    setTestState({ kind: 'running', message: 'Testing hosted MCP...' })
    try {
      const result = await window.omi.mcpKeyTest()
      if (runId !== testRunId.current) return
      setTestState({
        kind: 'success',
        message: `Connected. get_memories returned ${result.memoryCount} memor${result.memoryCount === 1 ? 'y' : 'ies'}.`
      })
    } catch (error) {
      if (runId !== testRunId.current) return
      setTestState({ kind: 'error', message: (error as Error).message })
    }
  }

  const hasKey = Boolean(storedKey)

  return (
    <section className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-white/45">
            <Server className="h-3.5 w-3.5" />
            Memory connectors
          </div>
          <h2 className="font-display text-lg font-semibold text-white">Connect Omi to AI apps</h2>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-white/55">
            Give ChatGPT, Claude, Claude Code, Codex, or another agent live access to your Omi
            memories through hosted MCP.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={generateKey}
            disabled={loadingKey || generating || testState.kind === 'running'}
            className="btn-primary inline-flex items-center gap-2 px-3 py-2 text-xs disabled:opacity-50"
          >
            {generating ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <KeyRound className="h-3.5 w-3.5" />
            )}
            {hasKey ? 'Regenerate key' : 'Generate key'}
          </button>
          <button
            onClick={testConnection}
            disabled={!hasKey || testState.kind === 'running'}
            className="btn-ghost inline-flex items-center gap-2 px-3 py-2 text-xs disabled:opacity-45"
          >
            {testState.kind === 'running' ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <TestTube2 className="h-3.5 w-3.5" />
            )}
            Test connection
          </button>
        </div>
      </div>

      {keyError && <div className="glass-subtle px-4 py-3 text-sm text-red-200/90">{keyError}</div>}
      {testState.kind !== 'idle' && (
        <div
          className={`glass-subtle px-4 py-3 text-sm ${
            testState.kind === 'success'
              ? 'text-emerald-200/90'
              : testState.kind === 'error'
                ? 'text-red-200/90'
                : 'text-white/60'
          }`}
        >
          {testState.message}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
        {mcpDestinations.map((destination) => (
          <DestinationButton
            key={destination.id}
            destination={destination}
            selected={destination.id === selectedId}
            onSelect={() => setSelectedId(destination.id)}
          />
        ))}
      </div>

      <div className="surface-card p-5">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h3 className="font-display text-base font-semibold text-white/95">
              {selectedDestination.title} setup
            </h3>
            <p className="mt-1 text-sm text-white/55">{selectedDestination.description}</p>
          </div>
          {setup.openURL && (
            <button
              onClick={() => window.open(setup.openURL, '_blank', 'noopener,noreferrer')}
              className="btn-ghost inline-flex shrink-0 items-center gap-2 px-3 py-2 text-xs"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              {setup.openTitle ?? `Open ${selectedDestination.title}`}
            </button>
          )}
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <div className="space-y-3">
            <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
              <div className="mb-3 text-xs font-semibold uppercase text-white/45">Steps</div>
              <ol className="space-y-2">
                {setup.steps.map((step, index) => (
                  <li key={step} className="flex gap-3 text-sm leading-relaxed text-white/65">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white/10 text-[11px] font-semibold text-white/70">
                      {index + 1}
                    </span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
            </div>
          </div>

          <div className="space-y-3">
            <CodeBlock
              title="Server URL"
              value={setup.serverURL}
              copyTarget={setup.serverURL}
              onCopy={copy}
            />
            {hasKey ? (
              <CodeBlock
                title="Your key"
                value={storedKey!.maskedKey}
                copyTarget={MCP_KEY_PLACEHOLDER}
                onCopy={copy}
              />
            ) : (
              <div className="rounded-2xl border border-white/10 bg-black/25 p-3 text-sm text-white/50">
                Generate a key to enable secure key copy and destination-specific commands.
              </div>
            )}
            {setup.copyText && (
              <CodeBlock
                title={setup.copyTitle ?? 'Setup text'}
                value={setup.copyText}
                copyTarget={setup.copyText}
                disabled={!hasKey}
                onCopy={copy}
              />
            )}
            {copyState && (
              <div className="flex items-center gap-2 text-xs text-emerald-200/90">
                <Check className="h-3.5 w-3.5" />
                Copied {copyState.label}
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
