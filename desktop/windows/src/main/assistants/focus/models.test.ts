// Response parse/validation: a structured-output model still occasionally
// returns prose, an empty part, or a status outside the enum — a bad answer must
// become "no verdict" (null), never a thrown error (that would spend a backoff
// cycle) and never a coerced verdict the model didn't make.
import { describe, expect, it } from 'vitest'
import { parseScreenAnalysis } from './models'

describe('parseScreenAnalysis', () => {
  it('parses a complete, valid response', () => {
    const a = parseScreenAnalysis(
      JSON.stringify({
        status: 'distracted',
        app_or_site: 'YouTube',
        description: 'watching a music video',
        message: 'Back to the PR?'
      })
    )
    expect(a).toEqual({
      status: 'distracted',
      appOrSite: 'YouTube',
      description: 'watching a music video',
      message: 'Back to the PR?'
    })
  })

  it('treats an absent message as null (it is optional)', () => {
    const a = parseScreenAnalysis(
      JSON.stringify({ status: 'focused', app_or_site: 'VS Code', description: 'editing' })
    )
    expect(a?.message).toBeNull()
    expect(a?.status).toBe('focused')
  })

  it('normalizes an empty-string message to null', () => {
    const a = parseScreenAnalysis(
      JSON.stringify({
        status: 'focused',
        app_or_site: 'VS Code',
        description: 'x',
        message: '   '
      })
    )
    expect(a?.message).toBeNull()
  })

  it('rejects a status outside the enum', () => {
    expect(
      parseScreenAnalysis(JSON.stringify({ status: 'neutral', app_or_site: 'X', description: 'y' }))
    ).toBeNull()
  })

  it('rejects a missing status', () => {
    expect(parseScreenAnalysis(JSON.stringify({ app_or_site: 'X', description: 'y' }))).toBeNull()
  })

  it('rejects non-JSON prose', () => {
    expect(parseScreenAnalysis('The user appears to be focused.')).toBeNull()
  })

  it('rejects a JSON array / non-object', () => {
    expect(parseScreenAnalysis('[]')).toBeNull()
    expect(parseScreenAnalysis('null')).toBeNull()
    expect(parseScreenAnalysis('42')).toBeNull()
  })

  it('tolerates missing app_or_site / description (only status is load-bearing)', () => {
    const a = parseScreenAnalysis(JSON.stringify({ status: 'focused' }))
    expect(a).toEqual({ status: 'focused', appOrSite: '', description: '', message: null })
  })
})
