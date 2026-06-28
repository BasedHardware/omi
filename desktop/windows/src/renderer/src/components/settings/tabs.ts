import {
  Settings as SettingsIcon,
  History,
  ShieldCheck,
  CircleUserRound,
  SlidersHorizontal,
  Brain,
  Cpu,
  Sparkles,
  type LucideIcon
} from 'lucide-react'

export type SettingsTabId =
  'general' | 'models' | 'memories' | 'rewind' | 'privacy' | 'pro' | 'account' | 'advanced'

export const SETTINGS_TABS: { id: SettingsTabId; label: string; Icon: LucideIcon }[] = [
  { id: 'general', label: 'General', Icon: SettingsIcon },
  { id: 'models', label: 'Models', Icon: Cpu },
  { id: 'memories', label: 'Memories', Icon: Brain },
  { id: 'rewind', label: 'Rewind', Icon: History },
  { id: 'privacy', label: 'Privacy', Icon: ShieldCheck },
  { id: 'pro', label: 'Cortex Pro', Icon: Sparkles },
  { id: 'account', label: 'Account', Icon: CircleUserRound },
  { id: 'advanced', label: 'Advanced', Icon: SlidersHorizontal }
]
