// The write side of the coding-agent command boundary. The stored string is
// handed to spawn(shell: true), so these cover what a renderer request may put
// there: the built-in suggested command, the value already stored, or a line the
// user approved in a native dialog — and nothing else.
import { describe, it, expect, beforeEach, afterAll, vi } from 'vitest'
import { mkdtempSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

const dir = mkdtempSync(join(tmpdir(), 'omi-coding-agent-ipc-'))
const showMessageBox = vi.hoisted(() => vi.fn(async () => ({ response: 1 })))

vi.mock('electron', () => ({
  app: { getPath: (): string => dir },
  globalShortcut: {
    register: (): boolean => true,
    unregister: (): void => {},
    isRegistered: (): boolean => false
  },
  ipcMain: { handle: (): void => {} },
  BrowserWindow: { getAllWindows: (): unknown[] => [] },
  dialog: { showMessageBox },
  shell: { openExternal: (): void => {} }
}))

import { authorizeAgentCommands } from './codingAgent'
import { SUGGESTED_AGENT_COMMANDS } from '../../shared/agentCommands'

afterAll(() => rmSync(dir, { recursive: true, force: true }))

const denied = vi.fn(async () => false)
const allowed = vi.fn(async () => true)

beforeEach(() => {
  denied.mockClear()
  allowed.mockClear()
  showMessageBox.mockClear()
})

describe('authorizeAgentCommands', () => {
  it('rejects an arbitrary renderer-supplied command without approval', async () => {
    const out = await authorizeAgentCommands({ codex: 'cmd /c start calc.exe' }, {}, denied)
    expect(out).toEqual({})
    expect(denied).toHaveBeenCalledWith('codex', 'cmd /c start calc.exe')
  })

  it('accepts the built-in suggested command with no prompt', async () => {
    const out = await authorizeAgentCommands(
      { codex: SUGGESTED_AGENT_COMMANDS.codex, openclaw: ` ${SUGGESTED_AGENT_COMMANDS.openclaw} ` },
      {},
      denied
    )
    expect(out).toEqual({
      codex: SUGGESTED_AGENT_COMMANDS.codex,
      openclaw: SUGGESTED_AGENT_COMMANDS.openclaw
    })
    expect(denied).not.toHaveBeenCalled()
  })

  it('re-saving the already-stored command needs no new approval', async () => {
    const out = await authorizeAgentCommands(
      { hermes: 'hermes --acp --custom' },
      { hermes: 'hermes --acp --custom' },
      denied
    )
    expect(out).toEqual({ hermes: 'hermes --acp --custom' })
    expect(denied).not.toHaveBeenCalled()
  })

  it('stores a custom command the user approved', async () => {
    const out = await authorizeAgentCommands({ hermes: 'hermes --acp --custom' }, {}, allowed)
    expect(out).toEqual({ hermes: 'hermes --acp --custom' })
    expect(allowed).toHaveBeenCalledWith('hermes', 'hermes --acp --custom')
  })

  it('a rejected overwrite leaves the previously stored command intact', async () => {
    const out = await authorizeAgentCommands(
      { codex: 'cmd /c start calc.exe' },
      { codex: SUGGESTED_AGENT_COMMANDS.codex },
      denied
    )
    expect(out).toEqual({ codex: SUGGESTED_AGENT_COMMANDS.codex })
  })

  it('omitting an id removes it (disconnect needs no approval)', async () => {
    const out = await authorizeAgentCommands({}, { codex: SUGGESTED_AGENT_COMMANDS.codex }, denied)
    expect(out).toEqual({})
    expect(denied).not.toHaveBeenCalled()
  })

  it('drops unknown ids, non-strings and blank values', async () => {
    const out = await authorizeAgentCommands(
      { evil: 'calc.exe', codex: 42, hermes: '   ' },
      {},
      denied
    )
    expect(out).toEqual({})
    expect(denied).not.toHaveBeenCalled()
  })

  it('treats a null/garbage patch as an empty one', async () => {
    expect(await authorizeAgentCommands(null, {}, denied)).toEqual({})
    expect(await authorizeAgentCommands('calc.exe', {}, denied)).toEqual({})
  })
})
