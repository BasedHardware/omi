import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AxiosError, type InternalAxiosRequestConfig } from 'axios'

const h = vi.hoisted(() => ({
  auth: { currentUser: null as null | { uid: string; getIdToken: () => Promise<string> } },
  refresh: vi.fn(),
  reauth: vi.fn()
}))
vi.mock('./firebase', () => ({ auth: h.auth }))
vi.mock('./authSession', () => ({ refreshIdToken: h.refresh, forceReauth: h.reauth }))
vi.mock('./clientDevice', () => ({ getWindowsDeviceIdHash: async () => 'test-device' }))
vi.mock('./byokKeys', () => ({ withByokHeadersIfActive: () => ({}) }))

import { omiApi } from './apiClient'
import { loadGoogleCalendarSelection, saveGoogleCalendarSelection } from './googleCalendarSelection'
const originalAdapter = omiApi.defaults.adapter
const data = {
  account_id: 'personal@example.test',
  calendars: [{ id: 'team', name: 'Team', primary: false, available: true }],
  selected_ids: ['team'],
  write_calendar_id: 'primary'
}
beforeEach(() => {
  h.auth.currentUser = { uid: 'owner', getIdToken: async () => 'synthetic-owner-token' }
  h.refresh.mockReset()
  h.reauth.mockReset()
})
afterEach(() => {
  omiApi.defaults.adapter = originalAdapter
})
const reply = (config: InternalAxiosRequestConfig) => ({
  data,
  status: 200,
  statusText: 'OK',
  headers: {},
  config
})

it('uses the production interceptor and catalog contract for load and save', async () => {
  const calls: InternalAxiosRequestConfig[] = []
  omiApi.defaults.adapter = async (config) => {
    calls.push(config)
    return reply(config)
  }
  const loaded = await loadGoogleCalendarSelection()
  await saveGoogleCalendarSelection(loaded, ['team'])
  expect(calls.map((c) => [c.method, c.url])).toEqual([
    ['get', '/v1/calendar/google/calendars'],
    ['put', '/v1/calendar/google/calendars']
  ])
  expect(JSON.parse(calls[1].data)).toEqual({ account_id: data.account_id, selected_ids: ['team'] })
  expect(calls[1].headers.Authorization).toBe('Bearer synthetic-owner-token')
})

it('an account change during token acquisition prevents dispatch', async () => {
  let release!: (value: string) => void
  const token = new Promise<string>((resolve) => {
    release = resolve
  })
  h.auth.currentUser!.getIdToken = () => token
  const dispatch = vi.fn(async (config) => reply(config))
  omiApi.defaults.adapter = dispatch
  const request = loadGoogleCalendarSelection()
  const refused = expect(request).rejects.toThrow('owner changed')
  await vi.waitFor(() => expect(release).toBeDefined())
  h.auth.currentUser = { uid: 'replacement', getIdToken: async () => 'other' }
  release('old')
  await refused
  expect(dispatch).not.toHaveBeenCalled()
})

it('a picker loaded by an old session cannot save as the replacement session', async () => {
  omiApi.defaults.adapter = async (config) => reply(config)
  const loaded = await loadGoogleCalendarSelection()
  const dispatch = vi.fn(async (config) => reply(config))
  omiApi.defaults.adapter = dispatch
  h.auth.currentUser = { uid: 'replacement', getIdToken: async () => 'other' }
  await expect(saveGoogleCalendarSelection(loaded, ['team'])).rejects.toThrow('owner changed')
  expect(dispatch).not.toHaveBeenCalled()
})

it('a 401 whose owner changed cannot retry or sign out the replacement account', async () => {
  omiApi.defaults.adapter = async (config) => {
    h.auth.currentUser = { uid: 'replacement', getIdToken: async () => 'other' }
    throw new AxiosError('401', '401', config, undefined, {
      data: {},
      status: 401,
      statusText: 'Unauthorized',
      headers: {},
      config
    })
  }
  await expect(loadGoogleCalendarSelection()).rejects.toBeDefined()
  expect(h.refresh).not.toHaveBeenCalled()
  expect(h.reauth).not.toHaveBeenCalled()
})
