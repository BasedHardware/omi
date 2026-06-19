import {
  Settings as SettingsIcon,
  History,
  ShieldCheck,
  CircleUserRound,
  SlidersHorizontal,
  Brain,
  Keyboard,
  Puzzle,
  Info,
  Key,
  Bell,
  Bluetooth,
  type LucideIcon
} from 'lucide-react'

export type SettingsTabId =
  | 'general'
  | 'memories'
  | 'rewind'
  | 'integrations'
  | 'shortcuts'
  | 'notifications'
  | 'devices'
  | 'privacy'
  | 'account'
  | 'advanced'
  | 'byok'
  | 'support'

export const SETTINGS_TABS: { id: SettingsTabId; label: string; Icon: LucideIcon }[] = [
  { id: 'general', label: 'General', Icon: SettingsIcon },
  { id: 'memories', label: 'Memories', Icon: Brain },
  { id: 'rewind', label: 'Rewind', Icon: History },
  { id: 'integrations', label: 'Integrations', Icon: Puzzle },
  { id: 'shortcuts', label: 'Shortcuts', Icon: Keyboard },
  { id: 'notifications', label: 'Notifications', Icon: Bell },
  { id: 'devices', label: 'Devices', Icon: Bluetooth },
  { id: 'privacy', label: 'Privacy', Icon: ShieldCheck },
  { id: 'account', label: 'Account', Icon: CircleUserRound },
  { id: 'advanced', label: 'Advanced', Icon: SlidersHorizontal },
  { id: 'byok', label: 'API Keys', Icon: Key },
  { id: 'support', label: 'Support', Icon: Info }
]
