export type SpeakerNameMap = Record<string, string>

const KEY = 'omi-windows-speaker-names-v1'

function allSpeakerNames(): Record<string, SpeakerNameMap> {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? '{}') as Record<string, SpeakerNameMap>
    return raw && typeof raw === 'object' ? raw : {}
  } catch {
    return {}
  }
}

export function speakerKey(label: string | undefined): string {
  return (label || 'speaker').trim() || 'speaker'
}

export function loadSpeakerNames(scope: string): SpeakerNameMap {
  return allSpeakerNames()[scope] ?? {}
}

export function saveSpeakerNames(scope: string, names: SpeakerNameMap): void {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...allSpeakerNames(), [scope]: names }))
  } catch {
    /* best-effort */
  }
}

export function displaySpeakerName(label: string | undefined, names: SpeakerNameMap): string {
  const key = speakerKey(label)
  return names[key]?.trim() || key
}
