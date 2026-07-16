import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import { toast } from '../../../../lib/toast'
import { useMemories } from '../../../../hooks/useMemories'
import { runMemoryPack } from '../../../../lib/mcpConnect'
import type { ExportMemory } from '../../../../../../shared/types'
import type { ConnectorBrand } from './ConnectorBrandMark'
import { ConnectorRow, PillButton } from './ConnectorRow'
import { ConnectorBrandMark } from './ConnectorBrandMark'

// The memory-PACK variant (Phase 2b): copy a prompt + your Markdown memory export
// to the clipboard and open the provider's chat, so you can paste it into a fresh
// conversation. Reuses the shared memory-export Markdown (main formats the pack +
// writes the clipboard + opens the chat). No hosted key, no OAuth.

// Gemini has no shipped brand asset (and must not borrow another provider's
// logo), so it renders a neutral lucide mark; ChatGPT/Claude use their brand mark.
const LABEL: Record<'gemini' | 'chatgpt' | 'claude', { title: string; brand?: ConnectorBrand }> = {
  gemini: { title: 'Gemini' },
  chatgpt: { title: 'ChatGPT', brand: 'chatgpt' },
  claude: { title: 'Claude', brand: 'claude' }
}

export function MemoryPackRow({
  provider
}: {
  provider: 'gemini' | 'chatgpt' | 'claude'
}): React.JSX.Element {
  const { memories } = useMemories()
  const [busy, setBusy] = useState(false)
  const { title, brand } = LABEL[provider]

  const run = async (): Promise<void> => {
    if (busy) return
    if (memories.length === 0) {
      toast('No memories to export yet', { tone: 'warn' })
      return
    }
    setBusy(true)
    try {
      const toExport: ExportMemory[] = memories.map((m) => ({
        content: m.content,
        category: m.category ?? null,
        createdAt: m.created_at
      }))
      await runMemoryPack(provider, toExport)
      toast(`Copied — paste into ${title}`, { tone: 'success' })
    } catch (e) {
      toast('Could not build the pack', { tone: 'error', body: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <ConnectorRow
      icon={brand ? undefined : Sparkles}
      iconNode={brand ? <ConnectorBrandMark brand={brand} /> : undefined}
      title={`Memory pack for ${title}`}
      description="Copy a prompt + your memories, then paste into a new chat"
      action={
        <PillButton tone="neutral" onClick={run} disabled={busy}>
          {busy ? 'Copying…' : 'Copy & open'}
        </PillButton>
      }
    />
  )
}
