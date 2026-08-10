import '@testing-library/jest-dom'
import { expect, test, vi } from 'vitest'
import { getQueriesForElement, render } from '@lynx-js/react/testing-library'

import { App } from '../App.jsx'

test('renders the honest disconnected companion home', async () => {
  const cb = vi.fn()
  render(<App onRender={() => cb(`__MAIN_THREAD__: ${__MAIN_THREAD__}`)} />)

  expect(cb).toHaveBeenCalled()
  expect(cb.mock.calls[0]?.[0]).toBe('__MAIN_THREAD__: false')

  const { findByText } = getQueriesForElement(elementTree.root!)
  expect(await findByText('Hi, I’m Omi')).toBeInTheDocument()
  expect(await findByText('Bluetooth is not connected')).toBeInTheDocument()
  expect(await findByText('Find my Omi')).toBeInTheDocument()
  expect(await findByText('Nearby Omi devices')).toBeInTheDocument()
  expect(await findByText(/real Omi GATT discovery/)).toBeInTheDocument()
})
