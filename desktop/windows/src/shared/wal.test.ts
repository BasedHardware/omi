import { describe, it, expect } from 'vitest'
import {
  WAL_MAX_AUTO_RETRIES,
  isWalDeletable,
  isWalPending,
  makeWalEntry,
  parseWalFileNameTimestamp,
  sanitizeWalDevice,
  walFileName,
  walId,
  walSyncDisplayState,
  type WalEntry,
  type WalStatus
} from './wal'

const entry = (over: Partial<WalEntry> = {}): WalEntry => ({
  ...makeWalEntry({
    timerStart: 1_723_800_000,
    codec: 'opus',
    seconds: 60,
    frameSize: 160,
    totalFrames: 6000
  }),
  ...over
})

describe('walSyncDisplayState', () => {
  it('splits a pending recording by how many attempts it has had', () => {
    expect(walSyncDisplayState(entry({ status: 'miss', retryCount: 0 }), false)).toBe('waiting')
    expect(walSyncDisplayState(entry({ status: 'miss', retryCount: 1 }), false)).toBe('retrying')
    expect(
      walSyncDisplayState(entry({ status: 'miss', retryCount: WAL_MAX_AUTO_RETRIES }), false)
    ).toBe('failed')
    expect(
      walSyncDisplayState(entry({ status: 'miss', retryCount: WAL_MAX_AUTO_RETRIES + 5 }), false)
    ).toBe('failed')
  })

  it('shows an active upload while one is running', () => {
    expect(walSyncDisplayState(entry({ status: 'miss' }), true)).toBe('syncing')
    expect(walSyncDisplayState(entry({ status: 'inProgress' }), false)).toBe('waiting')
  })

  it('keeps uploaded and synced distinct', () => {
    // "uploaded" means the server has the bytes but has not confirmed the
    // conversation, so it must not be presented as safely backed up.
    expect(walSyncDisplayState(entry({ status: 'uploaded' }), false)).toBe('uploaded')
    expect(walSyncDisplayState(entry({ status: 'synced' }), false)).toBe('synced')
  })

  it('terminal states outrank a stale syncing flag', () => {
    // An interrupted attempt can leave isSyncing set; a corrupted or refused
    // recording must never be downgraded to "uploading" by it.
    expect(walSyncDisplayState(entry({ status: 'corrupted' }), true)).toBe('corrupted')
    expect(walSyncDisplayState(entry({ status: 'outsideRecoveryWindow' }), true)).toBe(
      'outsideRecoveryWindow'
    )
  })
})

describe('pending and deletable', () => {
  it('only miss and inProgress still need an upload', () => {
    const pending: WalStatus[] = ['miss', 'inProgress']
    const notPending: WalStatus[] = ['uploaded', 'synced', 'corrupted', 'outsideRecoveryWindow']
    for (const status of pending) expect(isWalPending(entry({ status }))).toBe(true)
    for (const status of notPending) expect(isWalPending(entry({ status }))).toBe(false)
  })

  it('only a confirmed recording may be deleted', () => {
    expect(isWalDeletable(entry({ status: 'synced' }))).toBe(true)
    // The server has these bytes but the job can still fail, so deleting here
    // would lose the only copy of the audio.
    expect(isWalDeletable(entry({ status: 'uploaded' }))).toBe(false)
    expect(isWalDeletable(entry({ status: 'miss' }))).toBe(false)
    expect(isWalDeletable(entry({ status: 'outsideRecoveryWindow' }))).toBe(false)
  })
})

describe('identity', () => {
  it('is the capture source plus the start time', () => {
    expect(walId({ device: 'mic', timerStart: 42 })).toBe('mic_42')
  })
})

describe('upload filename contract', () => {
  it('builds the name the backend parses', () => {
    const name = walFileName({
      device: 'Omi-Mic',
      codec: 'opus',
      sampleRate: 16_000,
      channel: 1,
      frameSize: 160,
      timerStart: 1_723_800_000
    })
    expect(name).toBe('audio_omimic_opus_16000_1_fs160_1723800000.bin')
    // The whole point of the name: the server can read the capture time back.
    expect(parseWalFileNameTimestamp(name)).toBe(1_723_800_000)
  })

  it('sanitizes the device segment so it cannot break the field layout', () => {
    // A device name with underscores would otherwise move the timestamp out of
    // the last field and make every upload untrusted backfill.
    expect(sanitizeWalDevice('my_device 2.0')).toBe('mydevice20')
    const name = walFileName({
      device: 'my_device 2.0',
      codec: 'pcm16',
      sampleRate: 16_000,
      channel: 1,
      frameSize: 160,
      timerStart: 1_723_800_123
    })
    expect(parseWalFileNameTimestamp(name)).toBe(1_723_800_123)
  })

  it('reads millisecond timestamps as seconds', () => {
    expect(parseWalFileNameTimestamp('audio_mic_opus_16000_1_fs160_1723800000123.bin')).toBe(
      1_723_800_000.123
    )
  })

  it('accepts a bare timestamp name and a path', () => {
    expect(parseWalFileNameTimestamp('1723800000.wav')).toBe(1_723_800_000)
    expect(parseWalFileNameTimestamp('/tmp/x/audio_mic_opus_16000_1_fs160_1723800000.bin')).toBe(
      1_723_800_000
    )
  })

  it('rejects names with no usable timestamp', () => {
    for (const bad of ['audio_mic_opus.bin', 'audio_mic_opus_.bin', 'audio_mic_opus_0.bin', '']) {
      expect(parseWalFileNameTimestamp(bad)).toBeNull()
    }
    expect(parseWalFileNameTimestamp('audio_mic_opus_-5.bin')).toBeNull()
  })
})
