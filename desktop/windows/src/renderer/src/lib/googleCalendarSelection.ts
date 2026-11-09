import { omiApi } from './apiClient'
import { auth } from './firebase'
import type { User } from 'firebase/auth'
import type { AxiosRequestConfig } from 'axios'

export type ReadableGoogleCalendar = {
  id: string
  name: string
  primary: boolean
  available: boolean
}

export type GoogleCalendarSelection = {
  account_id: string
  calendars: ReadableGoogleCalendar[]
  selected_ids: string[]
  write_calendar_id: string
}

export type OwnedCalendarSelection = GoogleCalendarSelection & { owner: User }
const path = '/v1/calendar/google/calendars'

export async function loadGoogleCalendarSelection(): Promise<OwnedCalendarSelection> {
  const owner = auth.currentUser
  if (!owner) throw new Error('Sign in before choosing calendars')
  const __canSend = (): boolean => auth.currentUser === owner
  const config: AxiosRequestConfig & { __canSend: () => boolean } = { __canSend }
  const { data } = await omiApi.get<GoogleCalendarSelection>(path, config)
  if (!__canSend()) throw new Error('Request owner changed')
  return { ...data, owner }
}

export async function saveGoogleCalendarSelection(
  selection: OwnedCalendarSelection,
  selectedIDs: string[]
): Promise<OwnedCalendarSelection> {
  const __canSend = (): boolean => auth.currentUser === selection.owner
  if (!__canSend()) throw new Error('Request owner changed')
  const config: AxiosRequestConfig & { __canSend: () => boolean } = { __canSend }
  const { data } = await omiApi.put<GoogleCalendarSelection>(
    path,
    { account_id: selection.account_id, selected_ids: selectedIDs },
    config
  )
  if (!__canSend()) throw new Error('Request owner changed')
  return { ...data, owner: selection.owner }
}
