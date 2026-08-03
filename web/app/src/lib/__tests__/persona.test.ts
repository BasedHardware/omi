import { describe, expect, it } from 'vitest';
import { isPersonaPublic, personaPublicUrl, personaStatusLabel } from '@/lib/persona';

describe('personaPublicUrl', () => {
  it('points at the personas app', () => {
    expect(personaPublicUrl('ada')).toBe('https://personas.omi.me/u/ada');
  });

  it('encodes a username that would otherwise change the path', () => {
    expect(personaPublicUrl('a/b')).toBe('https://personas.omi.me/u/a%2Fb');
  });
});

describe('isPersonaPublic', () => {
  it('requires a username, approval, and not being private', () => {
    expect(isPersonaPublic({ username: 'ada', approved: true })).toBe(true);
  });

  it('is false without a username, because there is no URL to link to', () => {
    expect(isPersonaPublic({ approved: true })).toBe(false);
    expect(isPersonaPublic({ username: '', approved: true })).toBe(false);
  });

  it('is false while unapproved or private', () => {
    expect(isPersonaPublic({ username: 'ada', approved: false })).toBe(false);
    expect(isPersonaPublic({ username: 'ada' })).toBe(false);
    expect(isPersonaPublic({ username: 'ada', approved: true, private: true })).toBe(
      false,
    );
  });
});

describe('personaStatusLabel', () => {
  it('distinguishes the reasons a persona is not public', () => {
    expect(personaStatusLabel({ username: 'ada', approved: true })).toBe('Public');
    expect(personaStatusLabel({ username: 'ada', approved: true, private: true })).toBe(
      'Private',
    );
    expect(personaStatusLabel({ username: 'ada', approved: false })).toBe('Under review');
    expect(personaStatusLabel({ approved: true })).toBe('Not published');
  });
});
