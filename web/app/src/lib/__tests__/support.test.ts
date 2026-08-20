import { describe, expect, it } from 'vitest';
import { CRISP_WEBSITE_ID, crispEmbedUrl } from '@/lib/support';

describe('crispEmbedUrl', () => {
  it('targets the same Crisp workspace the desktop Help page uses', () => {
    expect(new URL(crispEmbedUrl()).searchParams.get('website_id')).toBe(
      CRISP_WEBSITE_ID,
    );
  });

  it('prefills who is asking', () => {
    const params = new URL(crispEmbedUrl({ email: 'a@example.com', name: 'Ada' }))
      .searchParams;

    expect(params.get('user_email')).toBe('a@example.com');
    expect(params.get('user_nickname')).toBe('Ada');
  });

  it('omits identity params rather than sending them empty', () => {
    const params = new URL(crispEmbedUrl({ email: null, name: '  ' })).searchParams;

    expect(params.has('user_email')).toBe(false);
    expect(params.has('user_nickname')).toBe(false);
  });

  it('encodes values that would otherwise break the query string', () => {
    const params = new URL(crispEmbedUrl({ email: 'a+b@example.com', name: 'Ada & Co' }))
      .searchParams;

    expect(params.get('user_email')).toBe('a+b@example.com');
    expect(params.get('user_nickname')).toBe('Ada & Co');
  });
});
