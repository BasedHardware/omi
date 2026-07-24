import type { ChatContentBlock } from '../../../../shared/chatContent'
import type { AgentThreadCardBlock } from '../../../../shared/types'
import { RevealMarkdown } from './RevealMarkdown'
import { AgentThreadCard } from './AgentThreadCard'
import { ThinkingBlock } from './ThinkingBlock'
import { ToolCallCard } from './ToolCallCard'
import { DiscoveryCard } from './DiscoveryCard'

/**
 * Renders one typed content block from an assistant message. This is the single
 * dispatch point that mirrors macOS ChatBubble's per-block rendering: text →
 * markdown, tool calls / thinking / discovery / agent cards → their own inline
 * components. The block union is the published contract (shared/chatContent.ts);
 * as the Windows agent runtime starts producing the richer block kinds, they
 * render here with no further wiring.
 */
export function ChatBlock({
  block,
  compact
}: {
  block: ChatContentBlock
  compact: boolean
}): React.JSX.Element | null {
  switch (block.type) {
    case 'text':
      // A settled text block (blocks are only assembled for finished turns).
      return <RevealMarkdown text={block.text} startRevealed />
    case 'thinking':
      return <ThinkingBlock block={block} compact={compact} />
    case 'toolCall':
      return <ToolCallCard block={block} compact={compact} />
    case 'discoveryCard':
      return <DiscoveryCard block={block} compact={compact} />
    case 'agentSpawn':
    case 'agentCompletion':
      return <AgentThreadCard block={block as AgentThreadCardBlock} compact={compact} />
    default:
      // Exhaustive today; a new block kind renders nothing until it gets a case
      // (never a crash).
      return null
  }
}
