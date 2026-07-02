import { it, expect } from 'vitest'
import { getPreferences, setPreferences } from './preferences'

// Node-env (the project's default Vitest environment): preferences keep an
// in-memory `current` object, so these assert the in-memory default + round-trip
// without touching localStorage (which doesn't exist under node — same approach
// as preferences.pendingRoute.test.ts).

it('continuousRecording defaults to false', () => {
  expect(getPreferences().continuousRecording ?? false).toBe(false)
})

it('continuousRecording round-trips through setPreferences', () => {
  setPreferences({ continuousRecording: true })
  expect(getPreferences().continuousRecording).toBe(true)
})

it('defaultModelByPurpose patches merge instead of replacing the map', () => {
  setPreferences({ defaultModelByPurpose: { chat: 'openai:gpt-4o', agent: 'openai:gpt-4o-mini' } })
  setPreferences({ defaultModelByPurpose: { memory: 'gemini:gemini-1.5-flash' } })
  expect(getPreferences().defaultModelByPurpose).toMatchObject({
    chat: 'openai:gpt-4o',
    agent: 'openai:gpt-4o-mini',
    memory: 'gemini:gemini-1.5-flash'
  })

  setPreferences({ defaultModelByPurpose: { agent: undefined } })
  expect(getPreferences().defaultModelByPurpose).toMatchObject({
    chat: 'openai:gpt-4o',
    memory: 'gemini:gemini-1.5-flash'
  })
  expect(getPreferences().defaultModelByPurpose?.agent).toBeUndefined()
})
