import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SearchBar } from '@/components/marketplace/SearchBar';

vi.mock('lodash/debounce', () => ({
  default: (fn: (...args: unknown[]) => unknown) => {
    const wrapped = (...args: unknown[]) => fn(...args);
    wrapped.cancel = () => {};
    return wrapped;
  },
}));

vi.mock('@/components/marketplace/plugin-card/CompactPluginCard', () => ({
  CompactPluginCard: ({ plugin }: { plugin: { id: string; name: string } }) => (
    <div data-testid="plugin-card">{plugin.name}</div>
  ),
}));

function type(value: string) {
  fireEvent.change(screen.getByPlaceholderText(/search apps/i), {
    target: { value },
  });
}

describe('SearchBar', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('tells the user when the search request fails instead of showing zero results', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) }),
    );

    render(<SearchBar />);
    type('notion');

    expect(await screen.findByRole('alert')).toHaveTextContent(/unavailable/i);
    expect(screen.queryByText(/Search Results \(0\)/)).not.toBeInTheDocument();
  });

  it('tells the user when the search request throws', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));

    render(<SearchBar />);
    type('notion');

    expect(await screen.findByRole('alert')).toHaveTextContent(/unavailable/i);
    expect(screen.queryByText(/Search Results \(0\)/)).not.toBeInTheDocument();
  });

  it('still reports a genuinely empty result set as zero results', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ results: [] }) }),
    );

    render(<SearchBar />);
    type('nothing matches this');

    expect(await screen.findByText(/Search Results \(0\)/)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('renders results and clears a previous failure on the next successful search', async () => {
    const fetchMock = vi.fn(async (url: string) =>
      url.includes('notion%20app')
        ? {
            ok: true,
            json: async () => ({
              results: [{ id: 'app-1', name: 'Notion', capabilities: ['memories'] }],
            }),
          }
        : { ok: false, status: 503, json: async () => ({}) },
    );
    vi.stubGlobal('fetch', fetchMock);

    render(<SearchBar />);
    type('notion');
    expect(await screen.findByRole('alert')).toBeInTheDocument();

    type('notion app');

    expect(await screen.findByTestId('plugin-card')).toHaveTextContent('Notion');
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  });
});
