import { useState } from 'react'
import { toast } from '../../../../lib/toast'
import { toastImportTally } from '../../../../lib/importToast'
import { useMemories } from '../../../../hooks/useMemories'
import type { MemorySource } from '../../../../lib/memoryExtract'
import {
  extractPasteMemories,
  importPasteMemories,
  toastForExtractResult
} from '../../../../lib/pasteImport'
import { ConnectorRow, PillButton } from './ConnectorRow'
import { ConnectorBrandMark } from './ConnectorBrandMark'
import { MemoryPreviewList } from './MemoryPreviewList'

// A ChatGPT / Claude memory-log paste connector, rendered once per source so the
// panel shows the two distinct rows Mac does. Clicking the row's action reveals an
// inline paste box (Windows' take on Mac's paste sheet); all extraction/fallback/
// import logic is shared via lib/pasteImport.ts.

const TITLE: Record<MemorySource, string> = {
  chatgpt: 'ChatGPT',
  claude: 'Claude'
}

export function PasteImportConnector({ source }: { source: MemorySource }): React.JSX.Element {
  const { memories, refresh } = useMemories()
  const [open, setOpen] = useState(false)
  const [dump, setDump] = useState('')
  const [parsed, setParsed] = useState<string[] | null>(null)
  const [profile, setProfile] = useState('')
  const [extracting, setExtracting] = useState(false)
  const [importing, setImporting] = useState(false)

  const extract = async (): Promise<void> => {
    if (!dump.trim() || extracting || importing) return
    setExtracting(true)
    setProfile('')
    try {
      const r = await extractPasteMemories(
        dump,
        source,
        memories.map((m) => m.content)
      )
      setParsed(r.memories)
      setProfile(r.profile)
      toastForExtractResult(r)
    } catch (e) {
      toast('Could not extract memories', { tone: 'error', body: (e as Error).message })
    } finally {
      setExtracting(false)
    }
  }

  const runImport = async (): Promise<void> => {
    if (!parsed || parsed.length === 0 || importing) return
    setImporting(true)
    const tally = await importPasteMemories(parsed)
    setImporting(false)
    toastImportTally(tally)
    if (tally.ok > 0) await refresh()
    if (!tally.failed) {
      setDump('')
      setParsed(null)
      setProfile('')
      setOpen(false)
    }
  }

  const title = TITLE[source]
  const count = parsed?.length ?? 0

  return (
    <ConnectorRow
      iconNode={<ConnectorBrandMark brand={source} />}
      title={title}
      description="Paste a memory export into Omi."
      action={
        <PillButton tone={open ? 'ghost' : 'primary'} onClick={() => setOpen((v) => !v)}>
          {open ? 'Close' : 'Connect'}
        </PillButton>
      }
    >
      {open && (
        <div className="space-y-2.5">
          <textarea
            value={dump}
            onChange={(e) => {
              setDump(e.target.value)
              setParsed(null)
              setProfile('')
            }}
            rows={4}
            placeholder={`Paste ${title}’s “everything you remember about me” reply here…`}
            className="input-field resize-none text-[13px]"
          />
          <div className="flex items-center gap-2">
            <PillButton
              tone="neutral"
              onClick={extract}
              disabled={!dump.trim() || extracting || importing}
            >
              {extracting ? 'Extracting…' : 'Extract memories'}
            </PillButton>
            {count > 0 && (
              <PillButton tone="primary" onClick={runImport} disabled={importing}>
                {importing ? 'Importing…' : `Import ${count}`}
              </PillButton>
            )}
          </div>
          {(profile || count > 0) && (
            <MemoryPreviewList profile={profile} memories={parsed ?? []} />
          )}
        </div>
      )}
    </ConnectorRow>
  )
}
