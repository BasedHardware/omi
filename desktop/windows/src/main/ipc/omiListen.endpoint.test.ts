import { describe, it, expect } from 'vitest'
import { buildListenEndpoint } from './omiListen'

describe('buildListenEndpoint', () => {
  it('conversation mode hits /v4/listen with the full pipeline params', () => {
    const url = buildListenEndpoint('conversation', 'en')
    expect(url).toContain('/v4/listen')
    expect(url).toContain('codec=pcm16')
    expect(url).toContain('include_speech_profile=true')
    expect(url).toContain('speaker_auto_assign=enabled')
    expect(url).toContain('source=desktop')
  })

  it('ptt mode hits the transcription-only endpoint (no conversation lifecycle)', () => {
    const url = buildListenEndpoint('ptt', 'en')
    expect(url).toContain('/v2/voice-message/transcribe-stream')
    // The bleed regression: PTT must NOT ride the /v4/listen conversation pipeline,
    // whose per-uid server-side conversation replayed a prior hold's segments into
    // the next capture.
    expect(url).not.toContain('/v4/listen')
    expect(url).not.toContain('include_speech_profile')
    expect(url).not.toContain('speaker_auto_assign')
  })

  it('ptt uses codec=linear16 — the transcribe-stream endpoint rejects pcm16 (1008)', () => {
    const url = buildListenEndpoint('ptt', 'en')
    expect(url).toContain('codec=linear16')
    expect(url).not.toContain('codec=pcm16')
  })

  it('carries the language through (defaulting to en) for both modes', () => {
    expect(buildListenEndpoint('ptt', 'es')).toContain('language=es')
    expect(buildListenEndpoint('conversation', 'es')).toContain('language=es')
    expect(buildListenEndpoint('ptt', '')).toContain('language=en')
  })
})
