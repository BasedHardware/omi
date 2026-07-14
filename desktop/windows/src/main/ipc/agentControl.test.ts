// Agent-control IPC surface tests.
//
// THE LOAD-BEARING ASSERTION HERE IS AN ABSENCE: the renderer must have no way
// to repoint the kernel's active owner. An earlier revision exposed
// `agentControl:setOwner`, which let a compromised or buggy renderer scope every
// subsequent control call to an arbitrary owner string — and the per-call owner
// guard was no defense, because it compares against whatever the renderer just
// set. These tests fail if that channel (or any owner-setting channel) comes
// back. Hermetic: electron is mocked, no kernel is constructed.

import { mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest'

const dir = mkdtempSync(join(tmpdir(), 'omi-agent-control-ipc-'))
const registeredChannels: string[] = []

vi.mock('electron', () => ({
  app: { getPath: (): string => dir },
  ipcMain: {
    handle: (channel: string): void => {
      registeredChannels.push(channel)
    }
  }
}))

import { registerAgentControlIpc } from './agentControl'
import { controlPlaneOwnerId, resetControlPlaneForTests } from '../agentKernel/controlPlane'
import { DEFAULT_LOCAL_OWNER_ID } from '../agentKernel/controlTools'

afterAll(() => rmSync(dir, { recursive: true, force: true }))

beforeEach(() => {
  registeredChannels.length = 0
  resetControlPlaneForTests()
})

describe('agent-control IPC surface', () => {
  it('exposes exactly the call and tools channels', () => {
    registerAgentControlIpc()
    expect([...registeredChannels].sort()).toEqual(['agentControl:call', 'agentControl:tools'])
  })

  it('exposes NO owner-setting channel — the renderer cannot repoint the kernel owner', () => {
    registerAgentControlIpc()

    expect(registeredChannels).not.toContain('agentControl:setOwner')
    // Deliberately broader than the one name: re-adding the setter under ANY
    // channel name fails here.
    expect(registeredChannels.filter((channel) => /owner/i.test(channel))).toEqual([])
  })

  it('the active owner is host-derived, not something IPC supplied', () => {
    registerAgentControlIpc()

    // Nothing the renderer can reach has set an owner, so control calls scope to
    // main's own default local owner.
    expect(controlPlaneOwnerId()).toBe(DEFAULT_LOCAL_OWNER_ID)
  })
})
