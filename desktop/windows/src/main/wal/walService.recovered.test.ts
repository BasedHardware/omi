// Storing audio recovered off a wearable's own storage. The service reaches
// Electron for the audio directory, so `app` is stubbed onto a real temp folder
// and everything else runs for real: a real sqlite db, real files on disk.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { DatabaseSync } from 'node:sqlite'
import { mkdtempSync, rmSync, existsSync, readFileSync, readdirSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

let userData = ''

vi.mock('electron', () => ({
  app: { getPath: () => userData },
  ipcMain: { handle: vi.fn(), on: vi.fn() }
}))
vi.mock('../appSettings', () => ({
  getAppSettings: () => ({ offlineCapture: {} }),
  setAppSettings: (patch: unknown) => patch
}))

const { WAL_SCHEMA, getWal, listPendingWals } = await import('./walStore')
type WalDb = Parameters<typeof getWal>[0]
const { WalService } = await import('./walService')
const { walId } = await import('../../shared/wal')

const EPOCH = 1_723_800_000

let database: InstanceType<typeof DatabaseSync>
let db: WalDb
let service: InstanceType<typeof WalService>

const recording = (
  over: Record<string, unknown> = {}
): Parameters<InstanceType<typeof WalService>['storeRecovered']>[0] => ({
  bytes: Uint8Array.from([1, 2, 3, 4]),
  timerStart: EPOCH,
  seconds: 180,
  totalFrames: 9000,
  codec: 'opus',
  sampleRate: 16_000,
  frameSize: 160,
  device: 'omi',
  ...over
})

beforeEach(() => {
  userData = mkdtempSync(join(tmpdir(), 'omi-wal-recovered-'))
  database = new DatabaseSync(':memory:')
  database.exec(WAL_SCHEMA)
  db = database as unknown as WalDb
  service = new WalService({
    db,
    getToken: async () => 'token',
    getDeviceIdHash: async () => 'hash',
    baseUrl: 'https://example.invalid',
    appVersion: '1.0.0',
    settings: () => ({ autoSync: false, retainEverything: false, retention: undefined as never }),
    broadcast: () => undefined
  })
})

afterEach(() => {
  database.close()
  rmSync(userData, { recursive: true, force: true })
})

describe('WalService.storeRecovered', () => {
  it('writes the audio and queues it for upload like any other missed recording', async () => {
    expect(await service.storeRecovered(recording())).toBe('stored')

    const entry = getWal(db, walId({ device: 'omi', timerStart: EPOCH }))
    expect(entry).toMatchObject({
      status: 'miss',
      storage: 'disk',
      codec: 'opus',
      seconds: 180,
      totalFrames: 9000,
      sizeBytes: 4
    })
    // The upload filename carries the capture time after the last underscore,
    // which is what the server reads it out of.
    expect(entry?.filePath).toBe('audio_omi_opus_16000_1_fs160_1723800000.bin')
    expect(readFileSync(join(userData, 'wal-audio', entry!.filePath!))).toEqual(
      Buffer.from([1, 2, 3, 4])
    )
    // The sync engine picks it up with no further prompting.
    expect(listPendingWals(db).map((e) => walId(e))).toEqual(['omi_1723800000'])
  })

  it('treats a recording it already holds as a duplicate and leaves it alone', async () => {
    await service.storeRecovered(recording())
    database.prepare(`UPDATE audio_wal SET status = 'synced'`).run()

    expect(await service.storeRecovered(recording())).toBe('duplicate')

    // An interrupted transfer re-reads records it already delivered. Storing it
    // again would put an uploaded recording back in the pending queue and
    // create a second conversation from the same audio.
    expect(getWal(db, 'omi_1723800000')?.status).toBe('synced')
    expect(listPendingWals(db)).toEqual([])
  })

  it('keeps recordings from the same device at different times apart', async () => {
    await service.storeRecovered(recording())
    expect(await service.storeRecovered(recording({ timerStart: EPOCH + 180 }))).toBe('stored')
    expect(listPendingWals(db).length).toBe(2)
    expect(readdirSync(join(userData, 'wal-audio')).length).toBe(2)
  })

  it('refuses a recording with no audio in it', async () => {
    expect(await service.storeRecovered(recording({ bytes: new Uint8Array(0) }))).toBe('failed')
    expect(await service.storeRecovered(recording({ totalFrames: 0 }))).toBe('failed')
    // Nothing is written and nothing is queued, so no empty upload is attempted.
    expect(listPendingWals(db)).toEqual([])
    expect(
      existsSync(join(userData, 'wal-audio', 'audio_omi_opus_16000_1_fs160_1723800000.bin'))
    ).toBe(false)
  })
})
