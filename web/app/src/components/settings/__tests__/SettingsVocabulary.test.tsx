import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

const { getCustomVocabulary, updateCustomVocabulary } = vi.hoisted(() => ({
  getCustomVocabulary: vi.fn(async (): Promise<string[] | null> => null),
  updateCustomVocabulary: vi.fn(async (_words: string[]) => {}),
}));

vi.mock('@tschk/moonshine-next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams('section=account'),
}));
vi.mock('@tschk/moonshine-next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock('@tschk/moonshine-next/image', () => ({
  default: (props: Record<string, unknown>) => <img {...props} alt="" />,
}));
vi.mock('@/components/auth/AuthProvider', () => ({
  useAuth: () => ({
    user: { uid: 'user-1', email: 'user@example.com', displayName: 'User' },
    signOut: vi.fn(),
  }),
}));
vi.mock('@/components/ui/Toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }));
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  getCustomVocabulary,
  updateCustomVocabulary,
}));

import { SettingsPage } from '@/components/settings/SettingsPage';

async function addWord(word: string) {
  const input = await screen.findByPlaceholderText('Enter a word or phrase');
  await waitFor(() => expect(getCustomVocabulary).toHaveBeenCalled());
  fireEvent.change(input, { target: { value: word } });
  fireEvent.click(within(input.parentElement!).getByRole('button'));
}

describe('Settings > Account > Custom Vocabulary', () => {
  beforeEach(() => {
    getCustomVocabulary.mockClear();
    updateCustomVocabulary.mockClear();
  });

  it('does not save anything when the load failed', async () => {
    getCustomVocabulary.mockRejectedValueOnce(new Error('offline'));
    render(<SettingsPage />);

    await addWord('omi');

    expect(updateCustomVocabulary).not.toHaveBeenCalled();
  });

  it('does not save anything when the list came back unknown', async () => {
    getCustomVocabulary.mockResolvedValueOnce(null);
    render(<SettingsPage />);

    await addWord('omi');

    expect(updateCustomVocabulary).not.toHaveBeenCalled();
  });

  it('saves the new word alongside the loaded ones', async () => {
    getCustomVocabulary.mockResolvedValueOnce(['alpha']);
    render(<SettingsPage />);

    await addWord('omi');

    await waitFor(() =>
      expect(updateCustomVocabulary).toHaveBeenCalledWith(['alpha', 'omi']),
    );
  });
});
