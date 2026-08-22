import { describe, expect, it, vi, afterEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';

vi.mock('@tschk/moonshine-next/navigation', () => ({
  useParams: () => ({ ref: 'FU-abc123' }),
}));
vi.mock('@/moonshine/register-client-route', () => ({
  registerMoonshineRoute: () => {},
}));
vi.mock('@/components/fair-use/CaseStatusView', () => ({
  CaseStatusView: ({ status }: { status: { stage: string } | null }) => (
    <div data-testid="case-view">{status ? status.stage : 'not-found'}</div>
  ),
}));

import CaseStatusPage from '@/app/case/[ref]/page';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('case status page', () => {
  it('reads the case status same-origin, not cross-origin at api.omi.me', async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL) =>
        new Response(
          JSON.stringify({
            case_ref: 'FU-abc123',
            stage: 'warning',
            message: 'x',
            created_at: '',
            updated_at: '',
          }),
          { headers: { 'content-type': 'application/json' } },
        ),
    );
    vi.stubGlobal('fetch', fetchMock);

    const { getByTestId } = render(<CaseStatusPage />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toBe('/api/proxy/public/v1/fair-use/case/FU-abc123/status');
    expect(url).not.toContain('api.omi.me');
    await waitFor(() => expect(getByTestId('case-view').textContent).toBe('warning'));
  });
});
