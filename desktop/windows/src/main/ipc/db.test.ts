import { describe, it, expect, vi, afterEach } from 'vitest'
import { join } from 'path'
import { existsSync, rmSync, mkdirSync } from 'fs'
import os from 'os'

// Generate a unique userData directory for each test run in the OS temp folder
const mockUserData = join(
  os.tmpdir(),
  `omi-db-test-${Date.now()}-${Math.random().toString(36).substring(7)}`
)

vi.mock('electron', () => ({
  app: {
    getPath: (name: string): string => {
      if (name === 'userData') return mockUserData
      return ''
    }
  }
}))

describe('db.ts isolation', () => {
  const originalEnv = process.env.OMI_DB_PATH

  afterEach(() => {
    process.env.OMI_DB_PATH = originalEnv
    // Gracefully attempt cleanup. If SQLite still holds a file lock, it will be cleaned up
    // by the OS eventually when the process exits.
    try {
      if (existsSync(mockUserData)) {
        rmSync(mockUserData, { recursive: true, force: true })
      }
    } catch {
      // Ignore resource busy errors
    }
  })

  it('uses OMI_DB_PATH when environment variable is set', async () => {
    if (!existsSync(mockUserData)) {
      mkdirSync(mockUserData, { recursive: true })
    }
    const tempDbPath = join(mockUserData, 'temp_bench.db')
    process.env.OMI_DB_PATH = tempDbPath

    // Dynamically import so it reads the env var we just set
    vi.resetModules()
    const { execSafeSelect } = await import('./db')

    const result = execSafeSelect('PRAGMA database_list')
    const dbFile = (result.rows[0] as { file: string }).file

    // Note: SQLite normalizes paths, we check absolute path equivalence
    expect(dbFile.toLowerCase()).toBe(tempDbPath.toLowerCase())
  })

  it('falls back to userData/omi.db when OMI_DB_PATH is unset', async () => {
    if (!existsSync(mockUserData)) {
      mkdirSync(mockUserData, { recursive: true })
    }
    delete process.env.OMI_DB_PATH

    vi.resetModules()
    const { execSafeSelect } = await import('./db')

    const result = execSafeSelect('PRAGMA database_list')
    const dbFile = (result.rows[0] as { file: string }).file

    const expectedDefault = join(mockUserData, 'omi.db')
    expect(dbFile.toLowerCase()).toBe(expectedDefault.toLowerCase())
  })
})
