// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen } from '@testing-library/react'
import { AutoCreatedTasksStep } from './AutoCreatedTasksStep'

afterEach(cleanup)

describe('AutoCreatedTasksStep', () => {
  it('completes onboarding once, even when the button is double-clicked', () => {
    const onFinish = vi.fn()
    render(<AutoCreatedTasksStep onFinish={onFinish} />)

    const button = screen.getByText('Take me to my tasks')
    fireEvent.click(button)
    fireEvent.click(button)

    expect(onFinish).toHaveBeenCalledTimes(1)
  })
})
