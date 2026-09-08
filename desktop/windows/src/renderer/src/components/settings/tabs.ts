import {
  Settings as SettingsIcon,
  History,
  ShieldCheck,
  CircleUserRound,
  SlidersHorizontal,
  Brain,
  Bot,
  AudioLines,
  CreditCard,
  Keyboard,
  Bell,
  Info,
  type LucideIcon
} from 'lucide-react'

export type SettingsTabId =
  | 'general'
  | 'memories'
  | 'agents'
  | 'transcription'
  | 'rewind'
  | 'notifications'
  | 'privacy'
  | 'account'
  | 'plan-usage'
  | 'shortcuts'
  | 'advanced'
  | 'about'

export const SETTINGS_TABS: { id: SettingsTabId; label: string; Icon: LucideIcon }[] = [
  { id: 'general', label: 'General', Icon: SettingsIcon },
  { id: 'memories', label: 'Memories', Icon: Brain },
  { id: 'agents', label: 'Agents', Icon: Bot },
  { id: 'transcription', label: 'Transcription', Icon: AudioLines },
  { id: 'rewind', label: 'Rewind', Icon: History },
  { id: 'notifications', label: 'Notifications', Icon: Bell },
  { id: 'privacy', label: 'Privacy', Icon: ShieldCheck },
  { id: 'account', label: 'Account', Icon: CircleUserRound },
  { id: 'plan-usage', label: 'Plan & Usage', Icon: CreditCard },
  { id: 'shortcuts', label: 'Shortcuts', Icon: Keyboard },
  { id: 'advanced', label: 'Advanced', Icon: SlidersHorizontal },
  { id: 'about', label: 'About', Icon: Info }
]
