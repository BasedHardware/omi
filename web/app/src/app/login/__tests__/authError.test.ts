import { describe, expect, it } from 'vitest';
import { getAuthErrorMessage } from '@/app/login/LoginClient';

describe('getAuthErrorMessage', () => {
  it('explains when the local preview does not have Firebase sign-in configured', () => {
    expect(getAuthErrorMessage({ code: 'auth/configuration-not-found' }, 'Google')).toBe(
      'Sign-in is not configured in this local preview.',
    );
  });

  it('explains a redirect the user backed out of, the way mobile signs in', () => {
    expect(
      getAuthErrorMessage({ code: 'auth/redirect-cancelled-by-user' }, 'Google'),
    ).toBe('The sign-in window was closed before sign-in finished.');
  });

  it('points an in-app browser at a browser that can sign in', () => {
    expect(
      getAuthErrorMessage(
        { code: 'auth/operation-not-supported-in-this-environment' },
        'Google',
      ),
    ).toBe(
      'This browser cannot open the sign-in window. Open app.omi.me in Safari or Chrome and try again.',
    );
  });

  it('names no provider for a redirect error, which arrives without one', () => {
    expect(getAuthErrorMessage({ code: 'auth/internal-error' })).toBe(
      'Sign-in failed. Please try again.',
    );
  });
});
