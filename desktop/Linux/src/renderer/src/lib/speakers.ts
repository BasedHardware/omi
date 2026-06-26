// Speaker naming, the Windows counterpart of LiveNameSpeakerSheet + person
// management. Persisted locally keyed by speaker id; also pushed to the backend
// people list (best-effort) so names survive across devices later.
import { api } from '../api/client'
import type { Person, ServerTranscriptSegment } from '../api/types'

const KEY = 'omi.speakerNames'
const PEOPLE_KEY = 'omi.peopleNames'

function read(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(KEY) || '{}')
  } catch {
    return {}
  }
}

function write(map: Record<string, string>): void {
  localStorage.setItem(KEY, JSON.stringify(map))
}

export function speakerName(speakerId: number | undefined): string | null {
  if (speakerId === undefined || speakerId === null) return null
  return read()[String(speakerId)] ?? null
}

export function setSpeakerName(speakerId: number, name: string): void {
  const map = read()
  const trimmed = name.trim()
  if (trimmed) map[String(speakerId)] = trimmed
  else delete map[String(speakerId)]
  write(map)
  if (trimmed) void api.createPerson(trimmed).catch(() => {})
}

// ---- People (backend speaker identities, the Mac NameSpeakerSheet's `people`) ----
// Cached locally so a name resolves immediately, refreshed from the backend on demand.

function readPeople(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(PEOPLE_KEY) || '{}')
  } catch {
    return {}
  }
}

function writePeople(map: Record<string, string>): void {
  localStorage.setItem(PEOPLE_KEY, JSON.stringify(map))
}

/** Locally cached people (id -> name), so transcript bubbles can label by person_id. */
export function cachedPeople(): Person[] {
  return Object.entries(readPeople()).map(([id, name]) => ({ id, name }))
}

/** Name for a backend person id, from the local people cache. */
export function personName(personId: string | null | undefined): string | null {
  if (!personId) return null
  return readPeople()[personId] ?? null
}

/** Pull the people list from the backend and refresh the local cache; returns the list. */
export async function loadPeople(): Promise<Person[]> {
  try {
    const people = await api.listPeople()
    const map: Record<string, string> = {}
    for (const p of people) map[p.id] = p.name
    writePeople(map)
    return people
  } catch {
    return cachedPeople()
  }
}

/** True if a (case-insensitive) name already exists in the given people list. */
export function isDuplicatePerson(name: string, people: Person[]): boolean {
  const trimmed = name.trim().toLowerCase()
  if (!trimmed) return false
  return people.some((p) => p.name.trim().toLowerCase() === trimmed)
}

/** Create a backend person and add it to the local cache; null on failure. */
export async function createPerson(name: string): Promise<Person | null> {
  const trimmed = name.trim()
  if (!trimmed) return null
  try {
    const person = await api.createPerson(trimmed)
    const map = readPeople()
    map[person.id] = person.name
    writePeople(map)
    return person
  } catch {
    return null
  }
}

/**
 * Assign a speaker to a set of transcript segments via the backend bulk-assign
 * endpoint (the Mac AppState.assignSpeakerToSegments path, PATCH
 * v1/conversations/{id}/segments/assign-bulk). `target` is either the current
 * user ("You") or a person id. Only segments with a backend id can be assigned
 * server-side; returns true if the call succeeded.
 */
export async function assignSpeakerToSegments(
  conversationId: string,
  segments: ServerTranscriptSegment[],
  target: { isUser: boolean; personId?: string | null }
): Promise<boolean> {
  const segmentIds = segments.map((s) => s.id).filter((id): id is string => !!id)
  if (segmentIds.length === 0) return false
  try {
    const res = await window.omi.api.request({
      method: 'PATCH',
      url: `v1/conversations/${conversationId}/segments/assign-bulk`,
      base: 'python',
      body: JSON.stringify({
        assign_type: target.isUser ? 'is_user' : 'person_id',
        value: target.isUser ? 'true' : (target.personId ?? 'null'),
        segment_ids: segmentIds
      })
    })
    return res.status >= 200 && res.status < 300
  } catch {
    return false
  }
}
