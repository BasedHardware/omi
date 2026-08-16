import { describe, expect, it } from 'vitest'
import { getWindowsDeviceIdHash, getWindowsInstallId } from './clientDevice'

function memoryStorage(): Pick<Storage, 'getItem' | 'setItem'> {
  const values = new Map<string, string>()
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value)
    }
  }
}

describe('Windows client device identity', () => {
  it('persists one install id rather than minting a new identity on each request', () => {
    const storage = memoryStorage()
    const generateId = () => 'windows-install-id'

    expect(getWindowsInstallId(storage, generateId)).toBe('windows-install-id')
    expect(getWindowsInstallId(storage, () => 'unexpected-new-id')).toBe('windows-install-id')
  })

  it('derives a stable eight-character provenance hash', async () => {
    const storage = memoryStorage()
    getWindowsInstallId(storage, () => 'windows-install-id')

    const first = await getWindowsDeviceIdHash(storage)
    const second = await getWindowsDeviceIdHash(storage)
    expect(first).toMatch(/^[0-9a-f]{8}$/)
    expect(second).toBe(first)
  })
})
