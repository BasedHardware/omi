import { describe, it, expect } from 'vitest'
import { parseWindowTitle } from './windowTitle'

describe('parseWindowTitle', () => {
  it('splits the trailing app segment off the title', () => {
    expect(parseWindowTitle('Inbox - Gmail - Google Chrome', 'chrome')).toEqual({
      app: 'Google Chrome',
      title: 'Inbox - Gmail'
    })
  })

  it('handles a simple "Doc - App" title', () => {
    expect(parseWindowTitle('Budget.xlsx - Excel', 'EXCEL')).toEqual({
      app: 'Excel',
      title: 'Budget.xlsx'
    })
  })

  it('falls back to the given app when there is no separator', () => {
    expect(parseWindowTitle('Settings', 'Explorer')).toEqual({
      app: 'Explorer',
      title: 'Settings'
    })
  })

  it('falls back to the given app for an empty title', () => {
    expect(parseWindowTitle('', 'Google Chrome')).toEqual({ app: 'Google Chrome', title: '' })
  })
})
