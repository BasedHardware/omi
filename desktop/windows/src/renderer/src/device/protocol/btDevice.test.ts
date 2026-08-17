import { describe, it, expect } from 'vitest'
import {
  detectDeviceType,
  isPlaudAdvertisement,
  makeBtDevice,
  shortDeviceId,
  displayModelNumber,
  displayFirmwareRevision,
  chooserFilters,
  type AdvertisementInput
} from './btDevice'
import { BEE_UUIDS, LIMITLESS_UUIDS, OMI_UUIDS, PLAUD_MANUFACTURER_ID } from './uuids'

const adv = (over: Partial<AdvertisementInput> = {}): AdvertisementInput => ({
  name: null,
  serviceUuids: [],
  ...over
})

describe('detectDeviceType', () => {
  it('matches by advertised service uuid per family', () => {
    expect(detectDeviceType(adv({ serviceUuids: [OMI_UUIDS.mainService] }))).toBe('omi')
    expect(detectDeviceType(adv({ serviceUuids: [BEE_UUIDS.service] }))).toBe('bee')
    expect(detectDeviceType(adv({ serviceUuids: [LIMITLESS_UUIDS.service] }))).toBe('limitless')
  })

  it('matches by name rules: contains, prefix, and exact per the mac order', () => {
    expect(detectDeviceType(adv({ name: 'Busy Bee 2' }))).toBe('bee')
    expect(detectDeviceType(adv({ name: 'PLAUD NotePin' }))).toBe('plaud')
    expect(detectDeviceType(adv({ name: 'compass' }))).toBe('fieldy')
    expect(detectDeviceType(adv({ name: 'friend_ab12' }))).toBe('friendPendant')
    expect(detectDeviceType(adv({ name: 'My Pendant' }))).toBe('limitless')
    expect(detectDeviceType(adv({ name: 'Some Random Speaker' }))).toBeNull()
  })

  it('order matters: a bee-named device with a limitless service is Bee (first match wins)', () => {
    expect(
      detectDeviceType(adv({ name: 'bee thing', serviceUuids: [LIMITLESS_UUIDS.service] }))
    ).toBe('bee')
  })

  it('order matters: Bee is checked before PLAUD, even on a PLAUD advertisement', () => {
    // Both rules match this advertisement; the mac order gives it to Bee.
    expect(
      detectDeviceType(
        adv({
          name: 'bee recorder',
          manufacturerData: new Map([[PLAUD_MANUFACTURER_ID, Uint8Array.from([0x04, 0x56])]])
        })
      )
    ).toBe('bee')
    expect(detectDeviceType(adv({ name: 'PLAUD Bee' }))).toBe('bee')
  })

  it('order matters: PLAUD is checked before Fieldy and Friend', () => {
    expect(detectDeviceType(adv({ name: 'plaud' }))).toBe('plaud')
    expect(
      detectDeviceType(
        adv({
          name: 'compass',
          manufacturerData: new Map([[PLAUD_MANUFACTURER_ID, Uint8Array.from([0x01])]])
        })
      )
    ).toBe('plaud')
    expect(
      detectDeviceType(
        adv({
          name: 'friend_01',
          manufacturerData: new Map([[PLAUD_MANUFACTURER_ID, Uint8Array.from([0x01])]])
        })
      )
    ).toBe('plaud')
  })

  it('order matters: Fieldy and Friend are checked before Limitless', () => {
    expect(
      detectDeviceType(adv({ name: 'compass', serviceUuids: [LIMITLESS_UUIDS.service] }))
    ).toBe('fieldy')
    expect(
      detectDeviceType(adv({ name: 'friend_pendant', serviceUuids: [LIMITLESS_UUIDS.service] }))
    ).toBe('friendPendant')
  })

  it('order matters: Limitless is checked before Omi and Frame', () => {
    expect(detectDeviceType(adv({ name: 'pendant', serviceUuids: [OMI_UUIDS.mainService] }))).toBe(
      'limitless'
    )
  })

  it('fieldy needs an exact name match, not contains', () => {
    expect(detectDeviceType(adv({ name: 'my compass' }))).toBeNull()
  })
})

describe('isPlaudAdvertisement', () => {
  it('recognizes the NotePin payload and any non-empty company-93 payload', () => {
    const notePin = new Map([[PLAUD_MANUFACTURER_ID, Uint8Array.from([0x04, 0x56, 0xcf, 0x00])]])
    expect(isPlaudAdvertisement(notePin)).toBe(true)
    const other = new Map([[PLAUD_MANUFACTURER_ID, Uint8Array.from([0x01])]])
    expect(isPlaudAdvertisement(other)).toBe(true)
    const empty = new Map([[PLAUD_MANUFACTURER_ID, new Uint8Array(0)]])
    expect(isPlaudAdvertisement(empty)).toBe(false)
    const wrongCompany = new Map([[94, Uint8Array.from([0x04, 0x56, 0xcf, 0x00])]])
    expect(isPlaudAdvertisement(wrongCompany)).toBe(false)
    expect(isPlaudAdvertisement(undefined)).toBe(false)
  })
})

describe('BtDevice model', () => {
  it('falls back to the type display name when the peripheral name is empty', () => {
    expect(makeBtDevice({ id: 'x', name: null, type: 'omi' }).name).toBe('omi')
    expect(makeBtDevice({ id: 'x', name: '', type: 'plaud' }).name).toBe('PLAUD')
    expect(makeBtDevice({ id: 'x', name: 'Omi CV1', type: 'omi' }).name).toBe('Omi CV1')
  })

  it('shortDeviceId takes the last 6 of the last dash component, else the first 6', () => {
    expect(shortDeviceId('19b10000-e8f2-537e-4f6c-d104768a1214')).toBe('8a1214')
    expect(shortDeviceId('ab:cd:ef')).toBe('abcdef')
    expect(shortDeviceId('a-b')).toBe('a-b')
  })

  it('display fallbacks use type defaults until device info is read', () => {
    const device = makeBtDevice({ id: 'x', name: 'omi', type: 'omi' })
    expect(displayModelNumber(device)).toBe('omi')
    expect(displayFirmwareRevision(device)).toBe('1.0.2')
    device.firmwareRevision = '2.1.1'
    expect(displayFirmwareRevision(device)).toBe('2.1.1')
  })
})

describe('chooserFilters', () => {
  it('covers every service-detected family and the name-prefix families', () => {
    const filters = chooserFilters()
    const services = filters.flatMap((f) => f.services ?? [])
    expect(services).toContain(OMI_UUIDS.mainService)
    expect(services).toContain(BEE_UUIDS.service)
    const prefixes = filters.map((f) => f.namePrefix).filter(Boolean)
    expect(prefixes).toContain('PLAUD')
    expect(prefixes).toContain('friend_')
  })
})
