import {
  AudioLines,
  BotMessageSquare,
  CreditCard,
  History,
  Info,
  Keyboard,
  ShieldCheck,
  CircleUserRound,
  SlidersHorizontal,
  Brain,
  KeyRound,
  type LucideIcon
} from 'lucide-react'

export type SettingsTabId =
  | 'ai-chat'
  | 'byok'
  | 'shortcuts'
  | 'transcription'
  | 'plan-usage'
  | 'about'
  | 'memories'
  | 'rewind'
  | 'privacy'
  | 'account'
  | 'advanced'

export const SETTINGS_TABS: { id: SettingsTabId; label: string; Icon: LucideIcon }[] = [
  { id: 'ai-chat', label: 'AI Chat', Icon: BotMessageSquare },
  { id: 'byok', label: 'BYOK', Icon: KeyRound },
  { id: 'shortcuts', label: 'Shortcuts', Icon: Keyboard },
  { id: 'transcription', label: 'Transcription', Icon: AudioLines },
  { id: 'plan-usage', label: 'Plan and Usage', Icon: CreditCard },
  { id: 'about', label: 'About', Icon: Info },
  { id: 'memories', label: 'Memories', Icon: Brain },
  { id: 'rewind', label: 'Rewind', Icon: History },
  { id: 'privacy', label: 'Privacy', Icon: ShieldCheck },
  { id: 'account', label: 'Account', Icon: CircleUserRound },
  { id: 'advanced', label: 'Advanced', Icon: SlidersHorizontal }
]
