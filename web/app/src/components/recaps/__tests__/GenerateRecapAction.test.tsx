import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { GenerateRecapAction } from '../GenerateRecapAction';
import { ApiHttpError } from '@/lib/api';
import type { DailySummary } from '@/types/recap';

vi.mock('@/lib/firebase', () => ({ getIdToken: vi.fn() }));

const recap = {
  id: 'recap-1',
  date: '2026-10-04',
  headline: 'Recovered day',
} as DailySummary;

function choose() {
  fireEvent.click(screen.getByRole('button', { name: 'Generate recap' }));
  fireEvent.change(screen.getByLabelText('Date'), { target: { value: '2026-10-04' } });
  return screen.getByRole('dialog');
}

describe('GenerateRecapAction', () => {
  it('creates an older missing recap once and opens the returned record', async () => {
    let complete!: (recap: DailySummary) => void;
    const generate = vi.fn(
      () =>
        new Promise<DailySummary>((resolve) => {
          complete = resolve;
        }),
    );
    const created = vi.fn();
    render(<GenerateRecapAction generate={generate} onCreated={created} />);
    const dialog = choose();
    const form = dialog.querySelector('form')!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(generate).toHaveBeenCalledTimes(1);
    expect(generate).toHaveBeenCalledWith('2026-10-04');
    expect(screen.getByRole('button', { name: 'Generating…' })).toBeDisabled();
    complete(recap);
    await waitFor(() => expect(created).toHaveBeenCalledWith(recap));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('cancel does not create or alter a recap', () => {
    const generate = vi.fn();
    render(<GenerateRecapAction generate={generate} onCreated={vi.fn()} />);
    choose();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(generate).not.toHaveBeenCalled();
  });

  it.each([
    [400, 'No completed conversations are ready to summarize'],
    [409, 'already being generated'],
    [429, 'Please wait'],
    [500, 'Check your connection'],
  ])('keeps the selected date and explains status %i', async (status, text) => {
    const created = vi.fn();
    render(
      <GenerateRecapAction
        generate={vi
          .fn()
          .mockRejectedValue(
            new ApiHttpError(status as number, 'internal server details'),
          )}
        onCreated={created}
      />,
    );
    const dialog = choose();
    fireEvent.submit(dialog.querySelector('form')!);
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(text as string),
    );
    expect(screen.getByLabelText('Date')).toHaveValue('2026-10-04');
    expect(screen.queryByText('internal server details')).not.toBeInTheDocument();
    expect(created).not.toHaveBeenCalled();
  });
});
