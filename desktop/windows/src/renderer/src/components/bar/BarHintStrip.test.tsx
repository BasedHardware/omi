// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, cleanup, screen } from '@testing-library/react'
import { BarHintStrip } from './BarHintStrip'

afterEach(() => cleanup())

describe('BarHintStrip (collapsed-pill PTT feedback)', () => {
  it('renders the hint text when a failed hold has one (Mac notch parity)', () => {
    // The too-short / dead-mic guidance the hook computes but the pill never showed.
    render(<BarHintStrip text="Hold longer to record" />)
    const strip = screen.getByRole('status')
    expect(strip.textContent).toBe('Hold longer to record')
    expect(strip.className).toContain('bar-hint')
  })

  it('renders the error text too — the same chip carries hint OR error', () => {
    render(<BarHintStrip text="Microphone unavailable" />)
    expect(screen.getByRole('status').textContent).toBe('Microphone unavailable')
  })

  it('renders NOTHING when there is no message — the success path is untouched', () => {
    // null (the common case: no failed hold) must paint no chip at all, so the
    // collapsed pill is byte-identical to today whenever nothing went wrong.
    const { container } = render(<BarHintStrip text={null} />)
    expect(container.firstChild).toBeNull()
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('renders nothing for an empty string as well (falsy guard)', () => {
    const { container } = render(<BarHintStrip text="" />)
    expect(container.firstChild).toBeNull()
  })
})
