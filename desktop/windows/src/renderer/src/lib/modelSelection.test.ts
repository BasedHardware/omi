import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ByokChatProvider, ByokProvider, ByokStatus } from '../../../shared/types'
import { setPreferences } from './preferences'
import { ByokCompletionError, resolveByokChatSelection, tryByokCompletion } from './modelSelection'

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

function installOmiMock(args: {
  byokStatus?: () => Promise<ByokStatus>
  byokChatSend?: () => Promise<{ text: string }>
}): void {
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      omi: {
        byokStatus: args.byokStatus ?? vi.fn(),
        byokChatSend: args.byokChatSend ?? vi.fn()
      }
    }
  })
}

beforeEach(() => {
  setPreferences({
    defaultModelByPurpose: { chat: undefined, agent: undefined, memory: undefined }
  })
})

afterEach(() => {
  vi.restoreAllMocks()
  setPreferences({
    defaultModelByPurpose: { chat: undefined, agent: undefined, memory: undefined }
  })
  Reflect.deleteProperty(globalThis, 'window')
})

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

describe('tryByokCompletion', () => {
  it('returns null when the purpose is not set to a BYOK model', async () => {
    const byokChatSend = vi.fn()
    installOmiMock({ byokChatSend })

    await expect(
      tryByokCompletion('agent', { messages: [{ role: 'user', content: 'plan' }] })
    ).resolves.toBeNull()
    expect(byokChatSend).not.toHaveBeenCalled()
  })

  it('uses the selected configured BYOK model', async () => {
    setPreferences({ defaultModelByPurpose: { agent: 'openai:gpt-4o-mini' } })
    const byokChatSend = vi.fn().mockResolvedValue({ text: 'agent output' })
    installOmiMock({
      byokStatus: vi.fn().mockResolvedValue(status('openai', ['openai'])),
      byokChatSend
    })

    await expect(
      tryByokCompletion('agent', { messages: [{ role: 'user', content: 'plan' }] })
    ).resolves.toBe('agent output')
    expect(byokChatSend).toHaveBeenCalledWith({
      messages: [{ role: 'user', content: 'plan' }],
      modelId: 'openai:gpt-4o-mini',
      systemPrompt: undefined,
      timeoutMs: undefined
    })
  })

  it('throws instead of allowing hosted fallback when the selected provider is not configured', async () => {
    setPreferences({ defaultModelByPurpose: { memory: 'gemini:gemini-1.5-flash' } })
    const byokChatSend = vi.fn()
    installOmiMock({
      byokStatus: vi.fn().mockResolvedValue(status(null, [])),
      byokChatSend
    })

    await expect(
      tryByokCompletion('memory', { messages: [{ role: 'user', content: 'private memory' }] })
    ).rejects.toThrow(ByokCompletionError)
    expect(byokChatSend).not.toHaveBeenCalled()
  })

  it('throws instead of allowing hosted fallback when the selected BYOK call fails', async () => {
    setPreferences({ defaultModelByPurpose: { memory: 'anthropic:claude-sonnet-4-5' } })
    installOmiMock({
      byokStatus: vi.fn().mockResolvedValue(status('anthropic', ['anthropic'])),
      byokChatSend: vi.fn().mockRejectedValue(new Error('provider timeout'))
    })

    await expect(
      tryByokCompletion('memory', { messages: [{ role: 'user', content: 'gmail summary' }] })
    ).rejects.toThrow('Anthropic BYOK request failed for memory: provider timeout')
  })
})
