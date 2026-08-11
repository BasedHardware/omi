import { describe, expect, it } from 'vitest';
import { getAuthErrorMessage } from '@/app/login/LoginClient';

describe('getAuthErrorMessage', () => {
  it('explains when the local preview does not have Firebase sign-in configured', () => {
    expect(getAuthErrorMessage({ code: 'auth/configuration-not-found' }, 'Google')).toBe(
      'Sign-in is not configured in this local preview.',
    );
  });
});
