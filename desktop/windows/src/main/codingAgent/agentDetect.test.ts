import { describe, it, expect, vi } from 'vitest'
import { detectAgentCli, detectAgents, parseVersion, type CommandRunner } from './agentDetect'

/** Fake runner: `--version` calls answer from `versionOut`/`versionCode`, the
 *  locate call (`where` / `command -v`) answers from `located`/`path`. */
function makeRunner(opts: {
  located?: boolean
  path?: string
  versionOut?: string
  versionCode?: number
}): CommandRunner {
  return async (command: string) => {
    if (command.includes('--version')) {
      return { code: opts.versionCode ?? 0, stdout: opts.versionOut ?? '', stderr: '' }
    }
    return opts.located
      ? { code: 0, stdout: opts.path ?? '/usr/bin/tool', stderr: '' }
      : { code: 1, stdout: '', stderr: '' }
  }
}

describe('parseVersion', () => {
  it('extracts a semver token from a chatty line', () => {
    expect(parseVersion('codex-cli 0.5.0')).toBe('0.5.0')
    expect(parseVersion('v1.2.3-beta.1 (build 9)')).toBe('1.2.3-beta.1')
  })
  it('falls back to the trimmed line (bounded) when there is no semver', () => {
    expect(parseVersion('  nightly  ')).toBe('nightly')
    expect(parseVersion('')).toBeUndefined()
    expect(parseVersion('x'.repeat(100))?.length).toBe(40)
  })
})

describe('detectAgentCli', () => {
  it('reports installed with path + parsed version', async () => {
    const det = await detectAgentCli(
      'codex',
      makeRunner({ located: true, path: 'C:\\bin\\codex.cmd', versionOut: 'codex-cli 0.5.0' })
    )
    expect(det).toEqual({ installed: true, path: 'C:\\bin\\codex.cmd', version: '0.5.0' })
  })

  it('reports not installed when locate fails', async () => {
    const det = await detectAgentCli('codex', makeRunner({ located: false }))
    expect(det).toEqual({ installed: false })
  })

  it('stays installed when the version probe fails (best-effort)', async () => {
    const det = await detectAgentCli(
      'hermes',
      makeRunner({ located: true, path: '/usr/bin/hermes', versionCode: 1 })
    )
    expect(det).toEqual({ installed: true, path: '/usr/bin/hermes', version: undefined })
  })

  it('takes only the first line of a multi-line where result', async () => {
    const det = await detectAgentCli(
      'openclaw',
      makeRunner({
        located: true,
        path: 'C:\\a\\openclaw.cmd\r\nC:\\b\\openclaw.ps1',
        versionOut: '1.0.0'
      })
    )
    expect(det.path).toBe('C:\\a\\openclaw.cmd')
  })

  it('refuses to shell out for an unsafe binary name (injection guard)', async () => {
    const run = vi.fn<CommandRunner>(async () => ({ code: 0, stdout: '', stderr: '' }))
    const det = await detectAgentCli('codex; rm -rf /', run)
    expect(det).toEqual({ installed: false })
    expect(run).not.toHaveBeenCalled()
  })
})

describe('detectAgents', () => {
  it('returns a detection for every external agent id', async () => {
    const result = await detectAgents(
      makeRunner({ located: true, path: '/x', versionOut: '2.0.0' })
    )
    expect(Object.keys(result).sort()).toEqual(['codex', 'hermes', 'openclaw'])
    expect(result.codex.installed).toBe(true)
    expect(result.codex.version).toBe('2.0.0')
  })
})
