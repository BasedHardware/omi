import type { ByokProvider, ByokValidationResult } from '../../shared/types'

type FetchLike = typeof fetch

export type ByokValidationOptions = {
  fetchImpl?: FetchLike
  timeoutMs?: number
}

type ValidationRequest = {
  url: string
  init: RequestInit
}

const VALIDATION_TIMEOUT_MS = 10_000

function keyFormatError(provider: ByokProvider): string {
  switch (provider) {
    case 'openai':
      return 'OpenAI keys should start with sk-'
    case 'anthropic':
      return 'Anthropic keys should start with sk-ant-'
    case 'gemini':
      return 'Gemini keys should be a Google API key'
    case 'deepgram':
      return 'Deepgram keys should be a token with no spaces'
    case 'openrouter':
      return 'OpenRouter keys should be a token with no spaces'
    case 'elevenlabs':
      return 'ElevenLabs keys should be a token with no spaces'
  }
}

function hasWhitespace(value: string): boolean {
  return /\s/.test(value)
}

function looksLikeProviderKey(provider: ByokProvider, key: string): boolean {
  if (key.length < 16 || hasWhitespace(key)) return false
  switch (provider) {
    case 'openai':
      return key.startsWith('sk-')
    case 'anthropic':
      return key.startsWith('sk-ant-')
    case 'gemini':
      return key.startsWith('AIza') || /^[A-Za-z0-9_-]{24,}$/.test(key)
    case 'deepgram':
      return /^[A-Za-z0-9._-]{20,}$/.test(key)
    case 'openrouter':
      return key.startsWith('sk-or-') || /^[A-Za-z0-9._-]{20,}$/.test(key)
    case 'elevenlabs':
      return key.startsWith('sk_') || /^[A-Za-z0-9._-]{20,}$/.test(key)
  }
}

export function buildByokValidationRequest(provider: ByokProvider, key: string): ValidationRequest {
  switch (provider) {
    case 'openai':
      return {
        url: 'https://api.openai.com/v1/models',
        init: {
          method: 'GET',
          headers: {
            authorization: `Bearer ${key}`
          }
        }
      }
    case 'anthropic':
      return {
        url: 'https://api.anthropic.com/v1/models',
        init: {
          method: 'GET',
          headers: {
            'anthropic-version': '2023-06-01',
            'x-api-key': key
          }
        }
      }
    case 'gemini':
      return {
        url: 'https://generativelanguage.googleapis.com/v1beta/models',
        init: {
          method: 'GET',
          headers: {
            'x-goog-api-key': key
          }
        }
      }
    case 'deepgram':
      return {
        url: 'https://api.deepgram.com/v1/projects',
        init: {
          method: 'GET',
          headers: {
            authorization: `Token ${key}`
          }
        }
      }
    case 'openrouter':
      return {
        url: 'https://openrouter.ai/api/v1/key',
        init: {
          method: 'GET',
          headers: {
            authorization: `Bearer ${key}`
          }
        }
      }
    case 'elevenlabs':
      return {
        url: 'https://api.elevenlabs.io/v1/models',
        init: {
          method: 'GET',
          headers: {
            'xi-api-key': key
          }
        }
      }
  }
}

export async function validateByokKey(
  provider: ByokProvider,
  key: string,
  options: ByokValidationOptions = {}
): Promise<ByokValidationResult> {
  const trimmed = key.trim()
  if (!looksLikeProviderKey(provider, trimmed)) {
    return { ok: false, error: keyFormatError(provider) }
  }

  const fetchImpl = options.fetchImpl ?? fetch
  const request = buildByokValidationRequest(provider, trimmed)
  const controller = new AbortController()
  const timeout = setTimeout(
    () => controller.abort(),
    Math.max(1, options.timeoutMs ?? VALIDATION_TIMEOUT_MS)
  )
  try {
    const response = await fetchImpl(request.url, { ...request.init, signal: controller.signal })
    if (response.ok) {
      return { ok: true, status: response.status }
    }
    return {
      ok: false,
      status: response.status,
      error:
        response.status === 401 || response.status === 403
          ? 'Provider rejected the key'
          : `Provider validation failed with HTTP ${response.status}`
    }
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      return { ok: false, error: 'Provider validation timed out' }
    }
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'Provider validation failed'
    }
  } finally {
    clearTimeout(timeout)
  }
}
