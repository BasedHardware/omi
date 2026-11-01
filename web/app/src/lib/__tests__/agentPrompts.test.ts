import { describe, expect, it } from 'vitest';
import {
  buildDevApiPrompt,
  buildMcpKeyPrompt,
  buildMcpOauthPrompt,
} from '@/lib/agentPrompts';
import { createZkrShare } from '@/lib/zkr';

const PROD = 'https://api.omi.me/';
const DEV = 'https://api.omiapi.com';
const MCP_KEY = 'omi_mcp_7f3c0a9e1b2d4c5e6f708192a3b4c5d6';
const DEV_KEY = 'omi_dev_0123456789abcdef0123456789abcdef';

async function shareOf(secret: string) {
  return createZkrShare(secret, {
    fetchImpl: async () => Response.json({ id: 'AbCdEfGhIjKlMnOpQrStUv', expiresAt: '' }),
  });
}

describe('agent prompts', () => {
  it('builds the OAuth prompt from the configured API base with no secret', () => {
    const prompt = buildMcpOauthPrompt(PROD);
    expect(prompt).toContain('Server: https://api.omi.me/v1/mcp');
    expect(prompt).toContain('/.well-known/oauth-protected-resource/v1/mcp');
    expect(prompt).toContain('Omi is my personal AI memory');
    expect(prompt).toContain('tools/list');
    expect(prompt).not.toMatch(/omi_(mcp|dev)_[A-Za-z0-9]/);
    expect(prompt).not.toContain('Bearer');
    expect(prompt).not.toContain('zkr');
  });

  it('hands dev hosts to dev builds', () => {
    for (const prompt of [
      buildMcpOauthPrompt(DEV),
      buildMcpKeyPrompt(DEV, { kind: 'pending' }),
      buildDevApiPrompt(DEV, { kind: 'pending' }),
    ]) {
      expect(prompt).toContain('https://api.omiapi.com/v1/');
      expect(prompt).not.toContain('api.omi.me/v1');
    }
  });

  it.each([
    [
      'MCP',
      MCP_KEY,
      (link: string) => buildMcpKeyPrompt(PROD, { kind: 'zkr', agentLink: link }),
    ],
    [
      'Developer API',
      DEV_KEY,
      (link: string) =>
        buildDevApiPrompt(PROD, { kind: 'zkr', agentLink: link }, ['memories:read']),
    ],
  ] as const)(
    '%s prompt carries the zkr agent link, never the key',
    async (_, key, build) => {
      const share = await shareOf(key);
      const prompt = build(share.agentLink);

      expect(prompt).toContain(share.agentLink);
      expect(prompt).not.toContain(key);
      expect(prompt).not.toContain(key.slice(8));
      expect(prompt).not.toContain(share.humanLink);
      expect(prompt).toContain('zkr receive --link-stdin --output');
      expect(prompt).toContain('https://zkr.scalingforever.com/llms.txt');
      expect(prompt).toMatch(/Never print, echo, log, or paste the key/);
      expect(prompt).toContain('Omi is my personal AI memory');
    },
  );

  it('tells the Developer API agent how to verify the key and which scopes it has', () => {
    const prompt = buildDevApiPrompt(PROD, { kind: 'pending' }, [
      'memories:read',
      'conversations:read',
    ]);
    expect(prompt).toContain('Base URL: https://api.omi.me/v1/dev');
    expect(prompt).toContain('GET https://api.omi.me/v1/dev/key');
    expect(prompt).toContain('Scopes on this key: memories:read, conversations:read');
    expect(prompt).toContain('starts with omi_dev_');
  });

  it('previews key prompts with a placeholder until a key exists', () => {
    const prompt = buildMcpKeyPrompt(PROD, { kind: 'pending' });
    expect(prompt).toContain('appears after you create a key');
    expect(prompt).not.toContain('zkr.scalingforever.com/a/');
  });
});
