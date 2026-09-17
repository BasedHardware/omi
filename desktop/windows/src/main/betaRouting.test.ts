import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function readEnvFile(name: string): Record<string, string> {
  const contents = readFileSync(resolve(__dirname, '../../', name), 'utf8')
  return Object.fromEntries(
    contents
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith('#') && line.includes('='))
      .map((line) => {
        const separator = line.indexOf('=')
        return [line.slice(0, separator), line.slice(separator + 1)]
      })
  )
}

describe('Windows release routing profiles', () => {
  it('keeps the stable profile on production services', () => {
    const env = readEnvFile('.env.example')
    expect(env.VITE_OMI_API_BASE).toBe('https://api.omi.me')
    expect(env.VITE_OMI_DESKTOP_API_BASE).toBe('https://desktop-backend-hhibjajaja-uc.a.run.app')
  })

  it('builds the Beta release against the development serving plane', () => {
    const env = readEnvFile('.env.beta.example')
    expect(env.VITE_OMI_API_BASE).toBe('https://api.omiapi.com')
    expect(env.VITE_OMI_DESKTOP_API_BASE).toBe('https://desktop-backend-dt5lrfkkoa-uc.a.run.app')
  })

  it('makes the existing release workflow consume the Beta profile', () => {
    const workflow = readFileSync(
      resolve(__dirname, '../../../../.github/workflows/desktop_windows_release.yml'),
      'utf8'
    )
    expect(workflow).toContain('Copy-Item .env.beta.example .env')
    expect(workflow).not.toContain('Copy-Item .env.example .env')
  })
})
