import { describe, expect, it } from 'vitest'
import type { ByokChatProvider, ByokProvider, ByokStatus } from '../../../shared/types'
import { resolveByokChatSelection } from './modelSelection'

const PROVIDERS: ByokProvider[] = [
  'openai',
  'anthropic',
  'gemini',
  'openrouter',
  'deepgram',
  'elevenlabs'
]

function status(
  activeChatProvider: ByokChatProvider | null,
  configured: ByokProvider[]
): ByokStatus {
  return {
    activeChatProvider,
    providers: Object.fromEntries(
      PROVIDERS.map((provider) => [
        provider,
        { provider, configured: configured.includes(provider) }
      ])
    ) as ByokStatus['providers']
  }
}

describe('resolveByokChatSelection', () => {
  it('uses the selected BYOK model only when that provider is configured', () => {
    expect(
      resolveByokChatSelection('openai:gpt-4o', status('gemini', ['openai', 'gemini']))
    ).toEqual({
      useByok: true,
      modelId: 'openai:gpt-4o'
    })
  })

  it('does not fall back to another active provider when selected provider is unconfigured', () => {
    expect(resolveByokChatSelection('openai:gpt-4o', status('gemini', ['gemini']))).toEqual({
      useByok: false
    })
  })

  it('uses the active provider only when no explicit model is selected', () => {
    expect(resolveByokChatSelection(undefined, status('gemini', ['gemini']))).toEqual({
      useByok: true
    })
  })

  it('keeps hosted Omi model selections on hosted chat', () => {
    expect(resolveByokChatSelection('omi:gpt-4o-mini', status('openai', ['openai']))).toEqual({
      useByok: false
    })
  })
})
