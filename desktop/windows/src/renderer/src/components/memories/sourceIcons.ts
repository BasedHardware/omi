// Icon per memory source kind. Lives apart from the components so component
// files export only components (react-refresh constraint).
import {
  Files,
  HelpCircle,
  LayoutGrid,
  Mail,
  MessageSquare,
  Mic,
  Monitor,
  Pencil,
  Plug,
  StickyNote,
  type LucideIcon
} from 'lucide-react'
import type { MemorySourceKind } from '../../lib/memoryProvenance'

export const SOURCE_ICONS: Record<MemorySourceKind, LucideIcon> = {
  screen: Monitor,
  conversation: Mic,
  chat: MessageSquare,
  manual: Pencil,
  gmail: Mail,
  'sticky-notes': StickyNote,
  'file-index': Files,
  integration: Plug,
  app: LayoutGrid,
  unknown: HelpCircle
}
