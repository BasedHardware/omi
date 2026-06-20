import { useState } from 'react'
import { X, Copy, Check, ExternalLink, BookOpen } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { Memory } from '../../hooks/useMemories'

type Destination = 'obsidian' | 'notion' | 'chatgpt' | 'claude' | 'agents'

const DESTINATIONS: { id: Destination; label: string; icon: string; description: string }[] = [
  { id: 'obsidian', label: 'Obsidian', icon: '💎', description: 'Export as Markdown to your vault' },
  { id: 'notion', label: 'Notion', icon: '📄', description: 'Copy as a Notion-ready Markdown block' },
  { id: 'chatgpt', label: 'ChatGPT', icon: '🤖', description: 'Copy as a memory injection prompt' },
  { id: 'claude', label: 'Claude', icon: '🧠', description: 'Copy as a context prompt for Claude' },
  { id: 'agents', label: 'Agents / MCP', icon: '⚡', description: 'Live connection via MCP server' },
]

function buildMemoryPack(memories: Memory[]): string {
  const lines = ['# Omi Memory Export', `Generated: ${new Date().toLocaleDateString()}`, '']
  const byCategory: Record<string, Memory[]> = {}
  for (const m of memories) {
    const cat = m.category ?? 'General'
    ;(byCategory[cat] ??= []).push(m)
  }
  for (const [cat, mems] of Object.entries(byCategory)) {
    lines.push(`## ${cat}`)
    for (const m of mems) {
      lines.push(`- ${m.content}`)
    }
    lines.push('')
  }
  return lines.join('\n')
}

function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }): React.JSX.Element {
  const [copied, setCopied] = useState(false)
  const copy = (): void => {
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }
  return (
    <button
      onClick={copy}
      className="flex items-center gap-2 rounded-xl bg-white/[0.08] px-4 py-2.5 text-sm font-medium text-white/80 transition-colors hover:bg-white/[0.12]"
    >
      {copied ? <Check className="h-4 w-4 text-green-400" /> : <Copy className="h-4 w-4" />}
      {copied ? 'Copied!' : label}
    </button>
  )
}

function ObsidianPanel({ memories }: { memories: Memory[] }): React.JSX.Element {
  const pack = buildMemoryPack(memories)
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-white/60">
        Copy your memories as Markdown and paste them into your Obsidian vault, or open the Omi folder directly.
      </p>
      <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-white/30">Memory Pack ({memories.length} memories)</p>
        <pre className="max-h-48 overflow-y-auto text-[11px] leading-relaxed text-white/50">{pack.slice(0, 800)}{pack.length > 800 ? '\n…' : ''}</pre>
      </div>
      <div className="flex gap-2">
        <CopyButton text={pack} label="Copy Markdown" />
        <button
          onClick={() => {
            const uri = `obsidian://new?name=Omi%2FMemories&content=${encodeURIComponent(pack)}`
            window.open(uri)
          }}
          className="flex items-center gap-2 rounded-xl border border-white/[0.08] bg-transparent px-4 py-2.5 text-sm font-medium text-white/60 transition-colors hover:border-white/20 hover:text-white/80"
        >
          <ExternalLink className="h-4 w-4" />
          Open in Obsidian
        </button>
      </div>
    </div>
  )
}

function NotionPanel({ memories }: { memories: Memory[] }): React.JSX.Element {
  const pack = buildMemoryPack(memories)
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-white/60">
        Copy your memories as Markdown, then paste them into a Notion page. Notion will auto-format the headings and bullet points.
      </p>
      <div className="flex gap-2">
        <CopyButton text={pack} label="Copy Memory Pack" />
        <button
          onClick={() => window.open('https://www.notion.so')}
          className="flex items-center gap-2 rounded-xl border border-white/[0.08] bg-transparent px-4 py-2.5 text-sm font-medium text-white/60 transition-colors hover:border-white/20 hover:text-white/80"
        >
          <ExternalLink className="h-4 w-4" />
          Open Notion
        </button>
      </div>
    </div>
  )
}

function ChatGPTPanel({ memories }: { memories: Memory[] }): React.JSX.Element {
  const pack = buildMemoryPack(memories)
  const prompt = `The following are my personal memories exported from Omi. Use them as context when answering my questions:\n\n${pack}`
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-white/60">
        Copy this context prompt and paste it at the start of a ChatGPT conversation (or add it as a custom instruction).
      </p>
      <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-white/30">Context Prompt</p>
        <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap text-[11px] leading-relaxed text-white/50">{prompt.slice(0, 600)}…</pre>
      </div>
      <div className="flex gap-2">
        <CopyButton text={prompt} label="Copy Context Prompt" />
        <button
          onClick={() => window.open('https://chat.openai.com')}
          className="flex items-center gap-2 rounded-xl border border-white/[0.08] bg-transparent px-4 py-2.5 text-sm font-medium text-white/60 transition-colors hover:border-white/20 hover:text-white/80"
        >
          <ExternalLink className="h-4 w-4" />
          Open ChatGPT
        </button>
      </div>
    </div>
  )
}

function ClaudePanel({ memories }: { memories: Memory[] }): React.JSX.Element {
  const pack = buildMemoryPack(memories)
  const prompt = `Here are my personal memories from Omi. Please use these as context for all of our conversations:\n\n${pack}`
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-white/60">
        Copy this context prompt and paste it into a new Claude project or conversation to give Claude access to your memories.
      </p>
      <div className="flex gap-2">
        <CopyButton text={prompt} label="Copy Context Prompt" />
        <button
          onClick={() => window.open('https://claude.ai')}
          className="flex items-center gap-2 rounded-xl border border-white/[0.08] bg-transparent px-4 py-2.5 text-sm font-medium text-white/60 transition-colors hover:border-white/20 hover:text-white/80"
        >
          <ExternalLink className="h-4 w-4" />
          Open Claude
        </button>
      </div>
    </div>
  )
}

function AgentsPanel(): React.JSX.Element {
  const mcpUrl = `https://api.omi.me/mcp/v1`
  const setupPrompt = `Connect to my Omi MCP server at ${mcpUrl} and read my memories, conversations, and tasks. Use omi_get_memories, omi_get_conversations, and omi_get_tasks tools.`
  return (
    <div className="flex flex-col gap-5">
      <p className="text-sm text-white/60">
        Connect your AI agent (Claude Code, Codex, Cursor, etc.) to Omi via the MCP server for live access to your memories and data.
      </p>

      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
        <p className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-white/35">MCP Server URL</p>
        <div className="flex items-center gap-2 rounded-lg bg-black/30 px-3 py-2">
          <code className="flex-1 font-mono text-[12px] text-[color:var(--accent)]">{mcpUrl}</code>
          <CopyButton text={mcpUrl} label="Copy" />
        </div>
      </div>

      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
        <p className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-white/35">Agent Setup Prompt</p>
        <p className="mb-2 text-xs text-white/40">Paste this into your agent to connect:</p>
        <pre className="mb-3 rounded-lg bg-black/30 p-3 text-[11px] leading-relaxed text-white/60 whitespace-pre-wrap">{setupPrompt}</pre>
        <CopyButton text={setupPrompt} label="Copy Setup Prompt" />
      </div>

      <div className="flex flex-col gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-white/35">Supported Agents</p>
        <div className="flex flex-wrap gap-2">
          {['Claude Code', 'Codex CLI', 'Cursor', 'Continue.dev', 'Cline'].map((name) => (
            <span key={name} className="rounded-full border border-white/[0.08] bg-white/[0.04] px-2.5 py-1 text-[11px] text-white/50">
              {name}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}

export function MemoryExportModal({
  memories,
  onClose
}: {
  memories: Memory[]
  onClose: () => void
}): React.JSX.Element {
  const [active, setActive] = useState<Destination>('obsidian')

  const dest = DESTINATIONS.find((d) => d.id === active)!

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="glass-strong flex h-[600px] w-[700px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-2xl shadow-2xl">
        {/* Header */}
        <div className="flex shrink-0 items-center gap-3 border-b border-white/[0.07] px-6 py-4">
          <BookOpen className="h-5 w-5 text-[color:var(--accent)]" strokeWidth={1.75} />
          <div className="flex-1">
            <h2 className="text-sm font-semibold text-white/90">Export Memories</h2>
            <p className="text-xs text-white/40">{memories.length} memories</p>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-white/30 transition-colors hover:bg-white/10 hover:text-white/70">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex min-h-0 flex-1 overflow-hidden">
          {/* Destination list */}
          <div className="flex w-[180px] shrink-0 flex-col gap-1 border-r border-white/[0.06] p-3">
            {DESTINATIONS.map((d) => (
              <button
                key={d.id}
                onClick={() => setActive(d.id)}
                className={cn(
                  'flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-left text-sm transition-colors',
                  active === d.id ? 'bg-white/10 text-white/90' : 'text-white/50 hover:bg-white/[0.05] hover:text-white/70'
                )}
              >
                <span className="text-base">{d.icon}</span>
                <span className="font-medium">{d.label}</span>
              </button>
            ))}
          </div>

          {/* Panel */}
          <div className="min-w-0 flex-1 overflow-y-auto p-6">
            <div className="mb-5">
              <div className="flex items-center gap-2">
                <span className="text-xl">{dest.icon}</span>
                <h3 className="text-base font-semibold text-white/90">{dest.label}</h3>
              </div>
              <p className="mt-1 text-xs text-white/40">{dest.description}</p>
            </div>
            {active === 'obsidian' && <ObsidianPanel memories={memories} />}
            {active === 'notion' && <NotionPanel memories={memories} />}
            {active === 'chatgpt' && <ChatGPTPanel memories={memories} />}
            {active === 'claude' && <ClaudePanel memories={memories} />}
            {active === 'agents' && <AgentsPanel />}
          </div>
        </div>
      </div>
    </div>
  )
}
