// Folder swatch palette. Neutral + warm/cool hues, deliberately NO purple/indigo
// (INV-UI-1 — purple is off-brand; the Track 4 purple ports are the selected-row
// tint and count badges only, not user folder colors). Backend default is #6B7280.
export const FOLDER_COLORS = [
  '#6B7280', // gray (default)
  '#EF4444', // red
  '#F97316', // orange
  '#F59E0B', // amber
  '#EAB308', // yellow
  '#10B981', // emerald
  '#14B8A6', // teal
  '#3B82F6', // blue
  '#0EA5E9', // sky
  '#EC4899' // pink
] as const

export const DEFAULT_FOLDER_COLOR = '#6B7280'
