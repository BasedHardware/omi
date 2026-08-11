import { createElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@tschk/moonshine-next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@tschk/moonshine-next/image', () => ({
  default: (props: Record<string, unknown>) =>
    createElement('img', { src: props.src, alt: props.alt }),
}));

vi.mock('@tschk/moonshine-next/link', () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) =>
    createElement('a', { href }, children),
}));

vi.mock('@/components/auth/AuthProvider', () => ({
  useAuth: () => ({
    user: null,
    loading: false,
    signInWithApple: vi.fn(),
    signInWithGoogle: vi.fn(),
  }),
}));

vi.mock('@/lib/firebase', () => ({
  isFirebaseAuthConfigured: false,
}));

vi.mock('@/lib/analytics/mixpanel', () => ({
  MixpanelManager: { pageView: vi.fn() },
}));

import { LoginClient } from '@/app/login/LoginClient';

describe('LoginClient geometry', () => {
  it('renders fixed auth actions, an out-of-flow status lane, and desktop mark clearance', () => {
    const markup = renderToStaticMarkup(createElement(LoginClient));

    expect(markup.match(/\bh-12\b/g)).toHaveLength(2);
    expect(markup).toContain('role="status"');
    expect(markup).toContain('absolute inset-x-0 top-full mt-3 h-[72px] w-full');
    expect(markup).toContain(
      'aria-hidden="true" class="mb-16 hidden h-16 w-16 sm:block"',
    );
    expect(markup).not.toContain('min-h-[52px]');
  });
});
