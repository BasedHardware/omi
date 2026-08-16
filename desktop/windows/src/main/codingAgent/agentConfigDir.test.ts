// Regression test for M1: Omi's Claude agent must use an ISOLATED config dir,
// never the user's real ~/.claude. Before the fix, claudeOAuth resolved to
// `CLAUDE_CONFIG_DIR ?? ~/.claude`, so on a machine where the user's own Claude
// Code CLI was logged in, Omi's sign-in overwrote their ~/.claude/.credentials
// and Omi's sign-out deleted it. These tests would have caught that: they prove
// the resolved path is under Omi's userData and that write/sign-out only ever
// touch the isolated dir.

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { existsSync, mkdtempSync, rmSync } from 'fs'
import { tmpdir, homedir } from 'os'
import { join } from 'path'
import { claudeAgentConfigDir, initClaudeAgentConfigDir } from './agentConfigDir'
import {
  claudeConfigDir,
  claudeCredentialsPath,
  writeClaudeCredentials,
  removeClaudeCredentials,
  readClaudeOauth
} from './claudeOAuth'

describe('claudeAgentConfigDir (pure resolver)', () => {
  it('resolves under the given userData dir, not ~/.claude', () => {
    const userData = join(tmpdir(), 'omi-userdata-fixture')
    const dir = claudeAgentConfigDir(userData)
    expect(dir).toBe(join(userData, 'claude-agent'))
    // Must NOT be the user's real Claude CLI dir.
    expect(dir).not.toBe(join(homedir(), '.claude'))
    expect(dir.startsWith(userData)).toBe(true)
  })
})

describe('initClaudeAgentConfigDir (isolation from ~/.claude)', () => {
  let priorConfigDir: string | undefined
  let userData: string | null = null

  beforeEach(() => {
    priorConfigDir = process.env.CLAUDE_CONFIG_DIR
    userData = mkdtempSync(join(tmpdir(), 'omi-userdata-'))
  })

  afterEach(() => {
    if (priorConfigDir === undefined) delete process.env.CLAUDE_CONFIG_DIR
    else process.env.CLAUDE_CONFIG_DIR = priorConfigDir
    if (userData) rmSync(userData, { recursive: true, force: true })
    userData = null
  })

  it('pins CLAUDE_CONFIG_DIR to the isolated dir and creates it', () => {
    const dir = initClaudeAgentConfigDir(userData!)
    expect(dir).toBe(join(userData!, 'claude-agent'))
    expect(process.env.CLAUDE_CONFIG_DIR).toBe(dir)
    expect(existsSync(dir)).toBe(true)
    // claudeOAuth (defaulting to process.env) now resolves into the isolated dir.
    expect(claudeConfigDir()).toBe(dir)
    expect(claudeCredentialsPath()).toBe(join(dir, '.credentials.json'))
  })

  it('overrides an inherited CLAUDE_CONFIG_DIR — isolation never defers to the user', () => {
    process.env.CLAUDE_CONFIG_DIR = join(homedir(), '.claude')
    const dir = initClaudeAgentConfigDir(userData!)
    expect(process.env.CLAUDE_CONFIG_DIR).toBe(dir)
    expect(process.env.CLAUDE_CONFIG_DIR).not.toBe(join(homedir(), '.claude'))
  })

  it('sign-in writes and sign-out removes creds ONLY in the isolated dir', () => {
    initClaudeAgentConfigDir(userData!)
    const isolated = claudeCredentialsPath()
    // Where the user's real CLI creds would live — must stay untouched.
    const realUserCreds = join(homedir(), '.claude', '.credentials.json')
    const realExistedBefore = existsSync(realUserCreds)

    writeClaudeCredentials({
      accessToken: 'AT',
      refreshToken: 'RT',
      expiresAt: Date.now() + 3_600_000,
      scopes: ['user:inference']
    })
    expect(existsSync(isolated)).toBe(true)
    expect(readClaudeOauth()?.accessToken).toBe('AT')
    // The user's real creds file was never created by Omi's write.
    expect(existsSync(realUserCreds)).toBe(realExistedBefore)

    removeClaudeCredentials()
    expect(readClaudeOauth()).toBeNull()
    // Sign-out did not create or touch the user's real creds file.
    expect(existsSync(realUserCreds)).toBe(realExistedBefore)
  })
})
