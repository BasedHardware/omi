// Per-session cache of the user's memories used by the local chat-grounding agent
// (localAgent.ts fetches once and reuses). Extracted to a leaf module (no apiClient
// import) so the sign-out teardown can clear it WITHOUT creating an import cycle
// through firebase → apiClient → authSession. Clearing it on sign-out stops a
// second account on the same machine from grounding chat in the prior user's
// memories. `import type` is erased at runtime, so this stays dependency-free.
import type { Memory } from '../hooks/useMemories'

let cache: Memory[] | null = null

export function getMemoryCache(): Memory[] | null {
  return cache
}

export function setMemoryCache(memories: Memory[]): void {
  cache = memories
}

export function clearMemoryCache(): void {
  cache = null
}
