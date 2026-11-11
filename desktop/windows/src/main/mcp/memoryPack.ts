// Memory-PACK export variant (Phase 2b) for the chat-first destinations: Gemini,
// and the ChatGPT/Claude "paste a pack" path. Builds a prompt preamble + the
// shared Markdown memory export, so the user can drop the whole thing into a
// fresh chat. Ported verbatim from macOS MemoryExportService.swift
// (manualPrompt + clipboardText + destinationURL).

import type { ExportMemory } from '../../shared/types'
import { formatMemoriesMarkdown } from '../memoryExport/format'

export type MemoryPackProvider = 'gemini' | 'chatgpt' | 'claude'

// The exact per-provider prompt preamble macOS prepends to the pack.
const PROMPTS: Record<MemoryPackProvider, string> = {
  chatgpt:
    'I’m attaching an Omi memory export. Read it carefully and keep the durable facts, preferences, projects, relationships, and goals as working context for future conversations with me. Start by giving me a concise profile summary of what you learned.',
  claude:
    'I’m attaching an Omi memory export. Absorb the durable facts about me, including projects, habits, preferences, relationships, and goals, and use them as context for future conversations. Start by summarizing the most important things you learned about me.',
  gemini:
    'I’m attaching an Omi memory export. Read it as persistent context about me and keep the durable facts, preferences, projects, and goals in mind for future chats. Start with a short profile summary of what stands out.'
}

// The chat the pack is meant to be pasted into (macOS destinationURL).
const CHAT_URLS: Record<MemoryPackProvider, string> = {
  chatgpt: 'https://chatgpt.com/',
  claude: 'https://claude.ai/new',
  gemini: 'https://gemini.google.com/app'
}

/** The clipboard text: prompt preamble + a `---` rule + the Markdown pack. */
export function buildMemoryPack(provider: MemoryPackProvider, memories: ExportMemory[]): string {
  const markdown = formatMemoriesMarkdown(memories)
  return `${PROMPTS[provider]}\n\n---\n\n${markdown}`
}

/** The provider chat URL to open after copying the pack. */
export function memoryPackChatUrl(provider: MemoryPackProvider): string {
  return CHAT_URLS[provider]
}
