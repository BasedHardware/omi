import { describe, expect, it } from 'vitest';
import { firebaseAuthDomain } from '../firebaseAuthDomain';

describe('Firebase redirect helper origin', () => {
  it('uses the production app origin with Firebase Hosting configuration', () => {
    expect(firebaseAuthDomain('based-hardware.firebaseapp.com', 'app.omi.me')).toBe(
      'app.omi.me',
    );
  });
  it('preserves local, preview and explicitly configured custom domains', () => {
    expect(firebaseAuthDomain('test.firebaseapp.com', 'localhost')).toBe(
      'test.firebaseapp.com',
    );
    expect(firebaseAuthDomain('preview.local', 'app.omi.me')).toBe('preview.local');
    expect(firebaseAuthDomain(undefined, 'app.omi.me')).toBeUndefined();
    expect(firebaseAuthDomain('auth.example.com', 'app.omi.me')).toBe('auth.example.com');
  });
});
