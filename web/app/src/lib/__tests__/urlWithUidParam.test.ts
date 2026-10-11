import { describe, expect, it } from 'vitest';
import { urlWithUidParam } from '@/lib/utils';

describe('urlWithUidParam', () => {
  it('adds uid as the query of a plain url', () => {
    expect(urlWithUidParam('https://ex.com/setup', 'u1')).toBe(
      'https://ex.com/setup?uid=u1',
    );
  });

  it('adds uid with & when the url already has a query', () => {
    expect(urlWithUidParam('https://ex.com/setup?source=omi', 'u1')).toBe(
      'https://ex.com/setup?source=omi&uid=u1',
    );
  });

  it('keeps existing query bytes and replaces a stale uid', () => {
    expect(urlWithUidParam('https://ex.com/setup?uid=old&sig=a%2Fb%3D&x=1+2', 'u1')).toBe(
      'https://ex.com/setup?sig=a%2Fb%3D&x=1+2&uid=u1',
    );
  });

  it('keeps the fragment after the query', () => {
    expect(urlWithUidParam('https://ex.com/setup?a=b#step2', 'u1')).toBe(
      'https://ex.com/setup?a=b&uid=u1#step2',
    );
  });

  it('encodes a uid with reserved characters', () => {
    const url = new URL(urlWithUidParam('https://ex.com/setup?a=b', 'u&x=1#f'));
    expect(url.searchParams.get('uid')).toBe('u&x=1#f');
    expect(url.searchParams.get('a')).toBe('b');
  });
});
