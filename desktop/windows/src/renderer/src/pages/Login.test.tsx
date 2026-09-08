// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'

const signInWithProvider = vi.hoisted(() => vi.fn())

vi.mock('../lib/firebase', () => ({ signInWithProvider }))

import { Login } from './Login'

beforeEach(() => {
  signInWithProvider.mockReset().mockResolvedValue({ uid: 'test-user' })
})

afterEach(() => {
  cleanup()
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

    await waitFor(() => expect(signInWithProvider).toHaveBeenCalledWith('apple'))
  })
})
