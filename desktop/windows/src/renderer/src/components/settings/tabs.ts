import {
  Settings as SettingsIcon,
  History,
  ShieldCheck,
  CircleUserRound,
  SlidersHorizontal,
  Brain,
  KeyRound,
  type LucideIcon
} from 'lucide-react'

export type SettingsTabId =
  | 'general'
  | 'byok'
  | 'memories'
  | 'rewind'
  | 'privacy'
  | 'account'
  | 'advanced'

export const SETTINGS_TABS: { id: SettingsTabId; label: string; Icon: LucideIcon }[] = [
  { id: 'general', label: 'General', Icon: SettingsIcon },
  { id: 'byok', label: 'BYOK', Icon: KeyRound },
  { id: 'memories', label: 'Memories', Icon: Brain },
  { id: 'rewind', label: 'Rewind', Icon: History },
  { id: 'privacy', label: 'Privacy', Icon: ShieldCheck },
  { id: 'account', label: 'Account', Icon: CircleUserRound },
  { id: 'advanced', label: 'Advanced', Icon: SlidersHorizontal }
]
