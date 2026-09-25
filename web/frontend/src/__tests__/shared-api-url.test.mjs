import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { sharedApiUrl } from '../lib/shared-api-url.mjs';

const BASE = 'https://api.example.com';

describe('sharedApiUrl', () => {
  it('joins fixed segments unchanged', () => {
    assert.equal(
      sharedApiUrl(BASE, 'v1', 'action-items', 'shared', 'tok123'),
      'https://api.example.com/v1/action-items/shared/tok123',
    );
  });

  it('encodes a slash inside a decoded route param', () => {
    // Next.js hands params decoded: /tasks/a%2Fb -> params.token === 'a/b'.
    assert.equal(
      sharedApiUrl(BASE, 'v1', 'action-items', 'shared', 'a/b'),
      'https://api.example.com/v1/action-items/shared/a%2Fb',
    );
  });

  it('encodes query and fragment characters', () => {
    assert.equal(
      sharedApiUrl(BASE, 'v2', 'messages', 'shared', 'x?y=1'),
      'https://api.example.com/v2/messages/shared/x%3Fy%3D1',
    );
    assert.equal(
      sharedApiUrl(BASE, 'v2', 'messages', 'shared', 'x#frag'),
      'https://api.example.com/v2/messages/shared/x%23frag',
    );
  });

  it('encodes params in the middle of a path', () => {
    assert.equal(
      sharedApiUrl(BASE, 'v1', 'conversations', 'a/b', 'shared'),
      'https://api.example.com/v1/conversations/a%2Fb/shared',
    );
  });

  it('strips a trailing slash on the base', () => {
    assert.equal(
      sharedApiUrl('https://api.example.com/', 'v1', 'shared', 't'),
      'https://api.example.com/v1/shared/t',
    );
  });
});
