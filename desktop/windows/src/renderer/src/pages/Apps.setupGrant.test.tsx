// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, waitFor, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Apps } from './Apps'

// First-time Install of a transport-backed integration from the Apps page. The catalog
// item is undecorated; setup and completion URLs carry one-use, account-bound grants
// that only a fresh GET /v1/apps/{id} returns. Every attempt must use a fresh grant,
// and nothing may launch, poll or enable after a failed read, an account change or
// an unmount.

const { getMock, postMock, toastMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn(),
  toastMock: vi.fn()
}))
vi.mock('../lib/apiClient', () => ({
  omiApi: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a)
  }
}))
vi.mock('../lib/toast', () => ({ toast: (...a: unknown[]) => toastMock(...a) }))

const CATALOG = {
  id: 'PCLOUD',
  name: 'pCloud Backup',
  category: 'other',
  capabilities: ['external_integration'],
  // Undecorated: no grant on either URL.
  external_integration: {
    auth_steps: [{ name: 'Connect', url: 'https://pcloud.example/setup/pcloud' }],
    setup_completed_url: 'https://pcloud.example/setup-completed'
  }
}

function signed(grant: number, withStatus = true): unknown {
  return {
    data: {
      ...CATALOG,
      external_integration: {
        auth_steps: [
          { name: 'Connect', url: `https://pcloud.example/setup/pcloud?omi_token=g${grant}%2Bsig` }
        ],
        setup_completed_url: withStatus
          ? `https://pcloud.example/setup-completed?omi_token=s${grant}%2Bsig`
          : null
      }
    }
  }
}

function seedGrid(uid = 'u1'): void {
  localStorage.setItem('omi.lastSignedInUid', uid)
  const section = {
    capabilityId: 'popular',
    title: 'Other',
    apps: [CATALOG],
    hasMore: false,
    total: 1,
    truncated: false
  }
  localStorage.setItem(
    `omi.cache.apps.${uid}`,
    JSON.stringify({
      sections: [section],
      allApps: [CATALOG],
      installedPool: [CATALOG],
      enabled: []
    })
  )
}

let openMock: ReturnType<typeof vi.fn>
let checkMock: ReturnType<typeof vi.fn>
let details: Array<() => Promise<unknown>>

beforeEach(() => {
  getMock.mockReset()
  postMock.mockReset()
  toastMock.mockReset()
  localStorage.clear()
  details = []
  getMock.mockImplementation((url: string) =>
    url === '/v1/apps/PCLOUD'
      ? (details.shift() ?? (() => Promise.reject(new Error('no detail'))))()
      : Promise.reject(new Error('offline'))
  )
  // The first enable fails until setup completes; later enables succeed.
  postMock.mockRejectedValueOnce({
    response: { status: 400, data: { detail: 'App setup is not completed' } }
  })
  openMock = vi.fn().mockResolvedValue(true)
  checkMock = vi.fn().mockResolvedValue(false)
  ;(window as unknown as { omi: unknown }).omi = {
    openExternalUrl: openMock,
    checkAppSetup: checkMock
  }
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

function renderApps(): ReturnType<typeof render> {
  return render(
    <MemoryRouter>
      <Apps />
    </MemoryRouter>
  )
}

async function clickInstall(): Promise<void> {
  fireEvent.click(await screen.findByRole('button', { name: 'Install' }))
}

describe('Apps — first-time Install uses fresh account-bound grants', () => {
  it('launches the fresh signed setup grant and polls the fresh signed status grant', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    seedGrid()
    details.push(() => Promise.resolve(signed(1)))
    checkMock.mockResolvedValue(true)
    postMock.mockResolvedValue({ data: {} })
    renderApps()
    await clickInstall()

    await waitFor(() =>
      expect(openMock).toHaveBeenCalledWith(
        'https://pcloud.example/setup/pcloud?omi_token=g1%2Bsig&uid=u1'
      )
    )
    await vi.advanceTimersByTimeAsync(3100)
    await waitFor(() =>
      expect(checkMock).toHaveBeenCalledWith({
        url: 'https://pcloud.example/setup-completed?omi_token=s1%2Bsig',
        uid: 'u1'
      })
    )
    await waitFor(() => expect(postMock).toHaveBeenCalledTimes(2))
    expect(openMock).not.toHaveBeenCalledWith(expect.stringContaining('/setup/pcloud?uid='))
  })

  it('fetches a new grant for a repeated attempt', async () => {
    seedGrid()
    details.push(() => Promise.resolve(signed(1, false)))
    details.push(() => Promise.resolve(signed(2, false)))
    postMock.mockRejectedValue({
      response: { status: 400, data: { detail: 'App setup is not completed' } }
    })
    renderApps()
    await clickInstall()
    await waitFor(() => expect(openMock).toHaveBeenCalledTimes(1))
    await clickInstall()
    await waitFor(() => expect(openMock).toHaveBeenCalledTimes(2))
    expect(openMock.mock.calls.map((c) => c[0])).toEqual([
      'https://pcloud.example/setup/pcloud?omi_token=g1%2Bsig&uid=u1',
      'https://pcloud.example/setup/pcloud?omi_token=g2%2Bsig&uid=u1'
    ])
  })

  it('a failed detail refresh launches nothing and leaves Install retryable', async () => {
    seedGrid()
    renderApps()
    await clickInstall()
    await waitFor(() =>
      expect(toastMock).toHaveBeenCalledWith('Couldn’t start setting up pCloud Backup', {
        tone: 'error',
        body: 'Try installing again.'
      })
    )
    expect(openMock).not.toHaveBeenCalled()
    expect(checkMock).not.toHaveBeenCalled()
    const retry = await screen.findByRole('button', { name: 'Install' })
    expect((retry as HTMLButtonElement).disabled).toBe(false)
  })

  it('an account change during the detail read launches nothing', async () => {
    seedGrid()
    let resolve: (v: unknown) => void = () => {}
    details.push(() => new Promise((r) => (resolve = r)))
    renderApps()
    await clickInstall()
    await waitFor(() => expect(getMock).toHaveBeenCalledWith('/v1/apps/PCLOUD'))
    localStorage.setItem('omi.lastSignedInUid', 'u2')
    resolve(signed(1))
    await new Promise((r) => setTimeout(r, 20))
    expect(openMock).not.toHaveBeenCalled()
    expect(toastMock).not.toHaveBeenCalled()
  })

  it('an unmount during the detail read launches nothing', async () => {
    seedGrid()
    let resolve: (v: unknown) => void = () => {}
    details.push(() => new Promise((r) => (resolve = r)))
    const view = renderApps()
    await clickInstall()
    await waitFor(() => expect(getMock).toHaveBeenCalledWith('/v1/apps/PCLOUD'))
    view.unmount()
    resolve(signed(1))
    await new Promise((r) => setTimeout(r, 20))
    expect(openMock).not.toHaveBeenCalled()
  })

  it('an account change while polling never enables the app for the new account', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    seedGrid()
    details.push(() => Promise.resolve(signed(1)))
    checkMock.mockResolvedValue(true)
    renderApps()
    await clickInstall()
    await waitFor(() => expect(openMock).toHaveBeenCalledTimes(1))
    localStorage.setItem('omi.lastSignedInUid', 'u2')
    await vi.advanceTimersByTimeAsync(3100)
    await waitFor(() => expect(checkMock).toHaveBeenCalled())
    await new Promise((r) => setTimeout(r, 20))
    expect(postMock).toHaveBeenCalledTimes(1) // only the original failed enable
  })
})
