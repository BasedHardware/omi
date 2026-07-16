import * as Tooltip from '@radix-ui/react-tooltip'
import { Info, ArrowUpRight, Monitor } from 'lucide-react'
import type { Memory } from '../../hooks/useMemories'
import {
  CATEGORY_LABEL,
  categoryOf,
  displayTags,
  formatMemoryDate,
  isNewMemory,
  isProtectedContent,
  layerLabel
} from '../../lib/memoryFilters'
import { Badge } from '../ui/Badge'
import { NewBadge } from './NewBadge'

// A compact "whichever apply" metadata row list for the hover info tooltip —
// the quick-peek surface, distinct from the full detail sheet a card tap opens.
function InfoRows({ memory }: { memory: Memory }): React.JSX.Element {
  const rows: Array<[string, string]> = []
  rows.push(['Category', CATEGORY_LABEL[categoryOf(memory)]])
  const layer = layerLabel(memory)
  if (layer) rows.push(['Layer', layer])
  if (memory.primary_capture_device) rows.push(['Device', memory.primary_capture_device])
  if (typeof memory.capture_confidence === 'number')
    rows.push(['Confidence', `${Math.round(memory.capture_confidence * 100)}%`])
  if (memory.app_id) rows.push(['App', memory.app_id])
  if (memory.conversation_id) rows.push(['Source', 'Conversation'])
  rows.push(['Created', formatMemoryDate(memory.created_at)])
  const tags = displayTags(memory)
  return (
    <div className="space-y-1.5">
      {rows.map(([k, v]) => (
        <div key={k} className="flex gap-3 text-xs">
          <span className="w-20 shrink-0 text-white/40">{k}</span>
          <span className="text-white/80">{v}</span>
        </div>
      ))}
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1 pt-1">
          {tags.map((t) => (
            <span key={t} className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-white/60">
              {t}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

type MemoryCardProps = {
  memory: Memory
  onOpen: (m: Memory) => void
  // Injected so a whole list shares one "now" and the New badge stays consistent.
  now?: number
}

// A tappable memory card: content preview + a metadata footer (date, category,
// tier badge, device, New badge, info tooltip). Tapping the body opens the
// detail sheet; the info button peeks metadata without leaving the list.
export function MemoryCard({ memory, onOpen, now }: MemoryCardProps): React.JSX.Element {
  const isNew = isNewMemory(memory, now)
  const protectedMem = isProtectedContent(memory.content)
  const layer = layerLabel(memory)
  const open = (): void => onOpen(memory)

  return (
    <li
      role="button"
      tabIndex={0}
      onClick={open}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          open()
        }
      }}
      className={`surface-card-interactive group cursor-pointer p-5 ${
        isNew ? 'bg-white/[0.06]' : ''
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        {protectedMem ? (
          <p className="italic text-white/40">Protected memory</p>
        ) : (
          <p className="line-clamp-2 text-sm leading-relaxed text-text-primary">{memory.content}</p>
        )}
        {isNew && (
          <span className="shrink-0">
            <NewBadge />
          </span>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-text-quaternary">
        <time>{formatMemoryDate(memory.created_at, now)}</time>
        <Badge tone="neutral" size="xs">
          {CATEGORY_LABEL[categoryOf(memory)]}
        </Badge>
        {layer && (
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] ${
              memory.layer === 'archive'
                ? 'bg-[var(--bg-raised)] text-white/70'
                : 'bg-[var(--bg-tertiary)] text-white/60'
            }`}
          >
            {layer}
          </span>
        )}
        {memory.primary_capture_device && (
          <span className="inline-flex items-center gap-1 text-text-quaternary">
            <Monitor className="h-3 w-3" aria-hidden />
            <span className="max-w-[8rem] truncate">{memory.primary_capture_device}</span>
          </span>
        )}

        <span className="ml-auto flex items-center gap-1">
          <Tooltip.Provider delayDuration={200} disableHoverableContent={false}>
            <Tooltip.Root>
              <Tooltip.Trigger asChild>
                <button
                  type="button"
                  onClick={(e) => e.stopPropagation()}
                  className="rounded-md p-1 text-white/30 transition-colors hover:bg-white/5 hover:text-white/70"
                  aria-label="Memory details"
                >
                  <Info className="h-3.5 w-3.5" />
                </button>
              </Tooltip.Trigger>
              <Tooltip.Portal>
                <Tooltip.Content
                  side="top"
                  align="end"
                  sideOffset={6}
                  className="z-[120] w-64 rounded-xl border border-white/10 bg-[var(--bg-secondary)] p-3 shadow-[0_12px_32px_rgba(0,0,0,0.5)]"
                >
                  <InfoRows memory={memory} />
                </Tooltip.Content>
              </Tooltip.Portal>
            </Tooltip.Root>
          </Tooltip.Provider>
          <ArrowUpRight className="h-3.5 w-3.5 text-white/25 opacity-0 transition-opacity group-hover:opacity-100" />
        </span>
      </div>
    </li>
  )
}
