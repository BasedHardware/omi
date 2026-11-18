// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { AiProfileCard } from './AiProfileCard'
import { aiProfileErrorMessage } from '../../../lib/aiProfileMessages'
import { SettingsSearchProvider } from '../SettingsSearchProvider'
import type { AiProfileErrorCode, AiUserProfile } from '../../../../../shared/types'

const profile: AiUserProfile = {
  profileText: 'Chris is a Windows developer who values understated UI.',
  dataSourcesUsed: 3,
  generatedAt: Date.UTC(2026, 6, 15),
  source: 'backend',
  refreshedAt: Date.UTC(2026, 6, 15)
}

const ok = <T,>(value: T): { ok: true; value: T } => ({ ok: true, value })
const fail = (code: AiProfileErrorCode): { ok: false; code: AiProfileErrorCode } => ({
  ok: false,
  code
})

const aiProfileGet = vi.fn()
const aiProfileRefresh = vi.fn()
const aiProfileEdit = vi.fn()
const aiProfileDelete = vi.fn()

const renderCard = (): void => {
  render(
    <SettingsSearchProvider>
      <AiProfileCard />
    </SettingsSearchProvider>
  )
}

beforeEach(() => {
  aiProfileGet.mockReset().mockResolvedValue(ok(profile))
  aiProfileRefresh.mockReset()
  aiProfileEdit.mockReset()
  aiProfileDelete.mockReset().mockResolvedValue(ok(null))
  ;(globalThis as unknown as { window: { omi: unknown } }).window.omi = {
    aiProfileGet,
    aiProfileRefresh,
    aiProfileEdit,
    aiProfileDelete
  }
})

afterEach(cleanup)

describe('AiProfileCard', () => {
  it('renders the cloud profile text and data-source count', async () => {
    renderCard()
    expect(await screen.findByText(profile.profileText)).toBeTruthy()
    expect(screen.getByText(/Data sources: 3 items/)).toBeTruthy()
  })

  it('shows the empty state with Generate Now when there is no profile', async () => {
    aiProfileGet.mockResolvedValue(ok(null))
    renderCard()
    expect(await screen.findByText('No profile yet.')).toBeTruthy()
    expect(screen.getByText('Generate Now')).toBeTruthy()
  })

  it('Regenerate calls the backend refresh and shows the returned profile', async () => {
    aiProfileRefresh.mockResolvedValue(ok({ ...profile, profileText: 'A fresher profile.' }))
    renderCard()
    fireEvent.click(await screen.findByText('Regenerate'))
    await waitFor(() => expect(aiProfileRefresh).toHaveBeenCalledTimes(1))
    expect(await screen.findByText('A fresher profile.')).toBeTruthy()
  })

  it('Edit → Save sends the edited text and shows the saved profile', async () => {
    aiProfileEdit.mockResolvedValue(
      ok({ ...profile, profileText: 'Edited profile.', source: 'user_edit' })
    )
    renderCard()
    fireEvent.click(await screen.findByText('Edit'))
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: 'Edited profile.' } })
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(aiProfileEdit).toHaveBeenCalledWith('Edited profile.'))
    expect(await screen.findByText('Edited profile.')).toBeTruthy()
  })

  it('Delete (after confirm) clears the profile', async () => {
    renderCard()
    fireEvent.click(await screen.findByText('Delete'))
    // Two-step confirm — nothing deleted until "Confirm delete".
    expect(aiProfileDelete).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText('Confirm delete'))
    await waitFor(() => expect(aiProfileDelete).toHaveBeenCalledTimes(1))
    expect(await screen.findByText('No profile yet.')).toBeTruthy()
  })

  it.each([
    ['usage_exhausted', /AI usage limit/],
    ['in_progress', /already updating your profile/],
    ['insufficient_data', /doesn't know enough about you yet/],
    ['synthesis_failed', /couldn't build your profile this time/]
  ] as const)('explains a %s refresh failure in plain English', async (code, line) => {
    aiProfileGet.mockResolvedValue(ok(null))
    aiProfileRefresh.mockResolvedValue(fail(code))
    renderCard()
    fireEvent.click(await screen.findByText('Generate Now'))
    await waitFor(() => expect(screen.getByText(line)).toBeTruthy())
  })

  it('never surfaces a raw Error when the IPC itself rejects', async () => {
    aiProfileGet.mockResolvedValue(ok(null))
    aiProfileRefresh.mockRejectedValue(new Error('backend body leak 500'))
    renderCard()
    fireEvent.click(await screen.findByText('Generate Now'))
    await waitFor(() =>
      expect(screen.getByText(/Couldn't generate a profile right now/)).toBeTruthy()
    )
    expect(screen.queryByText(/backend body leak/)).toBeNull()
  })

  it('keeps the profile on screen when a save fails', async () => {
    aiProfileEdit.mockResolvedValue(fail('network'))
    renderCard()
    fireEvent.click(await screen.findByText('Edit'))
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(screen.getByText(/Couldn't reach Omi/)).toBeTruthy())
    // Still in edit mode with the draft intact.
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe(profile.profileText)
  })
})

describe('aiProfileErrorMessage', () => {
  it('falls back to an action-specific line for an unknown failure', () => {
    expect(aiProfileErrorMessage('unknown', 'save')).toMatch(/Couldn't save your changes/)
    expect(aiProfileErrorMessage('unknown', 'delete')).toMatch(/Couldn't delete the profile/)
  })
})
