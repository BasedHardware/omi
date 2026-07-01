import {
  Settings as SettingsIcon,
  AudioLines,
  History,
  ShieldCheck,
  CircleUserRound,
  SlidersHorizontal,
  Brain,
  type LucideIcon
} from 'lucide-react'

export type SettingsTabId =
  | 'general'
  | 'memories'
  | 'rewind'
  | 'transcription'
  | 'privacy'
  | 'account'
  | 'advanced'

export const SETTINGS_TABS: { id: SettingsTabId; label: string; Icon: LucideIcon }[] = [
  { id: 'general', label: 'General', Icon: SettingsIcon },
  { id: 'memories', label: 'Memories', Icon: Brain },
  { id: 'rewind', label: 'Rewind', Icon: History },
  { id: 'transcription', label: 'Transcription', Icon: AudioLines },
  { id: 'privacy', label: 'Privacy', Icon: ShieldCheck },
  { id: 'account', label: 'Account', Icon: CircleUserRound },
  { id: 'advanced', label: 'Advanced', Icon: SlidersHorizontal }
]
