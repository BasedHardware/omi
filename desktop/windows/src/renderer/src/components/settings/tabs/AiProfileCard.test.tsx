// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { AiProfileCard } from './AiProfileCard'
import { SettingsSearchProvider } from '../SettingsSearchProvider'
import type { AiUserProfileRecord } from '../../../../../shared/types'

const record: AiUserProfileRecord = {
  id: 42,
  profileText: 'Chris is a Windows developer who values understated UI.',
  dataSourcesUsed: ['mem-1', 'mem-2', 'task-1'],
  generatedAt: Date.UTC(2026, 6, 15),
  backendSynced: true
}

const aiProfileGetLatest = vi.fn()
const aiProfileGenerateNow = vi.fn()
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
  aiProfileGetLatest.mockReset().mockResolvedValue(record)
  aiProfileGenerateNow.mockReset()
  aiProfileEdit.mockReset().mockResolvedValue(undefined)
  aiProfileDelete.mockReset().mockResolvedValue(undefined)
  ;(globalThis as unknown as { window: { omi: unknown } }).window.omi = {
    aiProfileGetLatest,
    aiProfileGenerateNow,
    aiProfileEdit,
    aiProfileDelete
  }
})

afterEach(cleanup)

describe('AiProfileCard', () => {
  it('renders the profile text and data-source count from getLatest', async () => {
    renderCard()
    expect(await screen.findByText(record.profileText)).toBeTruthy()
    // 3 sources → "Data sources: 3 items".
    expect(screen.getByText(/Data sources: 3 items/)).toBeTruthy()
  })

  it('shows the empty state with Generate Now when there is no profile', async () => {
    aiProfileGetLatest.mockResolvedValue(null)
    renderCard()
    expect(await screen.findByText('No profile yet.')).toBeTruthy()
    expect(screen.getByText('Generate Now')).toBeTruthy()
  })

  it('Regenerate calls generateNow and shows the returned profile', async () => {
    const regenerated: AiUserProfileRecord = {
      ...record,
      id: 43,
      profileText: 'A fresher profile.'
    }
    aiProfileGenerateNow.mockResolvedValue(regenerated)
    renderCard()
    fireEvent.click(await screen.findByText('Regenerate'))
    await waitFor(() => expect(aiProfileGenerateNow).toHaveBeenCalledTimes(1))
    expect(await screen.findByText('A fresher profile.')).toBeTruthy()
  })

  it('Edit → Save calls aiProfileEdit with the record id and the edited text', async () => {
    aiProfileGetLatest
      .mockResolvedValueOnce(record) // initial mount
      .mockResolvedValueOnce({ ...record, profileText: 'Edited profile.' }) // re-read after save
    renderCard()
    fireEvent.click(await screen.findByText('Edit'))
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: 'Edited profile.' } })
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(aiProfileEdit).toHaveBeenCalledWith(42, 'Edited profile.'))
    expect(await screen.findByText('Edited profile.')).toBeTruthy()
  })

  it('Delete (after confirm) calls aiProfileDelete with the record id', async () => {
    aiProfileGetLatest
      .mockResolvedValueOnce(record) // initial mount
      .mockResolvedValueOnce(null) // re-read after delete
    renderCard()
    fireEvent.click(await screen.findByText('Delete'))
    // Two-step confirm — nothing deleted until "Confirm delete".
    expect(aiProfileDelete).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText('Confirm delete'))
    await waitFor(() => expect(aiProfileDelete).toHaveBeenCalledWith(42))
    expect(await screen.findByText('No profile yet.')).toBeTruthy()
  })

  it('shows a plain-English error when generation fails (never a raw Error)', async () => {
    aiProfileGetLatest.mockResolvedValue(null)
    aiProfileGenerateNow.mockRejectedValue(new Error('backend body leak 500'))
    renderCard()
    fireEvent.click(await screen.findByText('Generate Now'))
    await waitFor(() =>
      expect(screen.getByText(/Couldn't generate a profile right now/)).toBeTruthy()
    )
    expect(screen.queryByText(/backend body leak/)).toBeNull()
  })
})
