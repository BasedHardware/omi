// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'

const h = vi.hoisted(() => ({
  signInWithProvider: vi.fn(),
  trackSignInStarted: vi.fn(),
  trackSignInCompleted: vi.fn(),
  trackSignInFailed: vi.fn()
}))

vi.mock('../lib/firebase', () => ({ signInWithProvider: h.signInWithProvider }))
vi.mock('../lib/analytics', () => ({
  trackSignInStarted: h.trackSignInStarted,
  trackSignInCompleted: h.trackSignInCompleted,
  trackSignInFailed: h.trackSignInFailed
}))

import { Login } from './Login'

beforeEach(() => {
  vi.clearAllMocks()
  h.signInWithProvider.mockResolvedValue({ uid: 'test-user' })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('Login page', () => {
  it('offers Apple before Google using the system-browser sign-in labels', () => {
    render(<Login />)

    const buttons = screen.getAllByRole('button')
    expect(buttons[0].textContent).toContain('Continue with Apple')
    expect(buttons[1].textContent).toContain('Continue with Google')
  })

  it('starts Apple sign-in through the shared provider bridge', async () => {
    render(<Login />)

    fireEvent.click(screen.getByRole('button', { name: 'Continue with Apple' }))

    await waitFor(() => expect(h.signInWithProvider).toHaveBeenCalledWith('apple'))
    expect(h.trackSignInStarted).toHaveBeenCalledWith('apple')
    expect(h.trackSignInCompleted).toHaveBeenCalledWith('apple')
    expect(h.trackSignInFailed).not.toHaveBeenCalled()
  })

  it('records a bounded failure through the analytics boundary', async () => {
    const error = new Error('Token exchange failed (500): private@example.com')
    h.signInWithProvider.mockRejectedValue(error)
    vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<Login />)

    fireEvent.click(screen.getByRole('button', { name: 'Continue with Google' }))

    await waitFor(() => expect(h.trackSignInFailed).toHaveBeenCalledWith('google', error))
    expect(h.trackSignInStarted).toHaveBeenCalledWith('google')
    expect(h.trackSignInCompleted).not.toHaveBeenCalled()
  })
})
