import { describe, expect, it } from 'vitest';
import { DEFAULT_AFTER_LOGIN, loginUrlReturningTo, safeNextPath } from '../loginNext';

describe('safeNextPath', () => {
  it('keeps same-origin app paths with their query', () => {
    expect(safeNextPath('/conversations?id=abc')).toBe('/conversations?id=abc');
    expect(safeNextPath('/tasks')).toBe('/tasks');
  });

  it('falls back to Home for anything that could leave the app', () => {
    for (const raw of [
      null,
      undefined,
      '',
      'conversations',
      '//evil.example/x',
      'https://evil.example',
      '/\\evil.example',
      'javascript:alert(1)',
      '/\u0000//evil.example',
      // URL normalization turns these into protocol-relative URLs.
      '/.//evil.example',
      '/.//evil.example/phish',
      '/%2f%2fevil.example',
      '/%2F%2Fevil.example/phish',
      '/%5C%5Cevil.example',
      '/%09//evil.example',
      '/%6cogin',
    ]) {
      expect(safeNextPath(raw)).toBe(DEFAULT_AFTER_LOGIN);
    }
  });

  it('never loops back to login', () => {
    expect(safeNextPath('/login?next=/tasks')).toBe(DEFAULT_AFTER_LOGIN);
  });
});

describe('loginUrlReturningTo', () => {
  it('encodes the return path', () => {
    expect(loginUrlReturningTo('/conversations?id=abc')).toBe(
      '/login?next=%2Fconversations%3Fid%3Dabc',
    );
  });

  it('omits next when it would only go Home', () => {
    expect(loginUrlReturningTo('/home')).toBe('/login');
    expect(loginUrlReturningTo('//evil.example')).toBe('/login');
  });
});
