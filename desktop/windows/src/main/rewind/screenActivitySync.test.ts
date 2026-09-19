import { describe, expect, it } from 'vitest'
import {
  boundedDeviceRetentionSeconds,
  buildScreenActivitySyncPayload,
  clientDeviceIdFromInstallId,
  formatScreenActivityTimestamp,
  parseAccountGeneration,
  resolveWindowsClientDeviceId
} from './screenActivitySyncLogic'
import type { ScreenActivitySyncCandidate } from '../ipc/db'

describe('screenActivitySync helpers', () => {
  it('formats timestamps in backend lexicographic UTC shape', () => {
    expect(formatScreenActivityTimestamp(Date.UTC(2026, 0, 15, 12, 30, 45, 7))).toBe(
      '2026-01-15 12:30:45.007'
    )
  })

  it('derives a stable windows client device id', () => {
    expect(clientDeviceIdFromInstallId('fixed-install')).toBe(
      clientDeviceIdFromInstallId('fixed-install')
    )
    expect(clientDeviceIdFromInstallId('fixed-install')).toMatch(/^windows_[a-f0-9]{8}$/)
  })

  it('persists install id in app_meta on first use', () => {
    const store = new Map<string, string>()
    const id = resolveWindowsClientDeviceId(
      (k) => store.get(k) ?? null,
      (k, v) => store.set(k, v),
      () => 'test-install-uuid'
    )
    expect(id).toBe(clientDeviceIdFromInstallId('test-install-uuid'))
    expect(store.get('windows-install-id')).toBe('test-install-uuid')
  })

  it('bounds device retention to six days', () => {
    expect(boundedDeviceRetentionSeconds(14)).toBe(6 * 24 * 60 * 60)
    expect(boundedDeviceRetentionSeconds(2)).toBe(2 * 24 * 60 * 60)
    expect(boundedDeviceRetentionSeconds(1)).toBe(24 * 60 * 60)
    expect(boundedDeviceRetentionSeconds(0)).toBeUndefined()
    expect(boundedDeviceRetentionSeconds(-1)).toBeUndefined()
  })

  it('parses server-authoritative cutover generation', () => {
    expect(parseAccountGeneration({ account_generation: 7 })).toBe(7)
    expect(parseAccountGeneration({ account_generation: 0 })).toBe(0)
    expect(parseAccountGeneration({ account_generation: -1 })).toBeNull()
    expect(parseAccountGeneration({ account_generation: 1.5 })).toBeNull()
    expect(parseAccountGeneration({})).toBeNull()
    expect(parseAccountGeneration(null)).toBeNull()
  })

  it('builds sync payload with macOS-parity retention and generation', () => {
    const candidates: ScreenActivitySyncCandidate[] = [
      {
        id: 42,
        ts: Date.UTC(2026, 0, 15, 12, 0, 0),
        app: 'Code',
        windowTitle: 'main.ts',
        ocrText: 'function hello() {}',
        priorState: 0,
        embedding: null
      }
    ]
    const payload = buildScreenActivitySyncPayload(candidates, {
      clientDeviceId: 'windows_abcd1234',
      deviceName: 'DESKTOP-TEST',
      accountGeneration: 7,
      retentionDays: 14
    })
    expect(payload).toEqual({
      account_generation: 7,
      deviceRetentionSeconds: 6 * 24 * 60 * 60,
      rows: [
        expect.objectContaining({
          id: 42,
          appName: 'Code',
          windowTitle: 'main.ts',
          clientDeviceId: 'windows_abcd1234',
          deviceName: 'DESKTOP-TEST'
        })
      ]
    })
    expect(payload.rows[0].embedding).toBeUndefined()
    expect(payload.rows[0]).not.toHaveProperty('captureEligible')
  })

  it('omits deviceRetentionSeconds when Rewind retention is unlimited', () => {
    const payload = buildScreenActivitySyncPayload(
      [
        {
          id: 1,
          ts: Date.UTC(2026, 0, 15, 12, 0, 0),
          app: 'Code',
          windowTitle: 'main.ts',
          ocrText: 'hi',
          priorState: 0,
          embedding: null
        }
      ],
      {
        clientDeviceId: 'windows_abcd1234',
        deviceName: 'DESKTOP-TEST',
        accountGeneration: 0,
        retentionDays: 0
      }
    )
    expect(payload.account_generation).toBe(0)
    expect(payload).not.toHaveProperty('deviceRetentionSeconds')
  })
})
