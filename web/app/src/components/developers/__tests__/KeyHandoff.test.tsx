import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { KeyHandoff } from '@/components/developers/KeyHandoff';
import { buildMcpKeyPrompt } from '@/lib/agentPrompts';
import { developerRedirectTarget } from '@/lib/settingsSections';

const KEY = 'omi_mcp_7f3c0a9e1b2d4c5e6f708192a3b4c5d6';
const LINK = 'https://zkr.scalingforever.com/a/AbCdEfGhIjKlMnOpQrStUv#v1.kkk.ttt';

function renderHandoff(
  createShare = vi.fn(async () => ({
    id: 'AbCdEfGhIjKlMnOpQrStUv',
    expiresAt: '',
    agentLink: LINK,
    humanLink: LINK.replace('/a/', '/h/'),
  })),
) {
  render(
    <KeyHandoff
      secret={KEY}
      keyLabel="MCP Key"
      buildPrompt={(source) => buildMcpKeyPrompt('https://api.omi.me', source)}
      onDone={vi.fn()}
      createShare={createShare}
    />,
  );
  return createShare;
}

describe('KeyHandoff', () => {
  it('leads with the secure link and keeps the raw key out of view', () => {
    renderHandoff();
    expect(
      screen.getByRole('button', { name: 'Send to My Agent Securely' }),
    ).toBeTruthy();
    expect(document.body.textContent).not.toContain(KEY);
  });

  it('builds the prompt around the zkr agent link, not the key', async () => {
    const createShare = renderHandoff();
    fireEvent.click(screen.getByRole('button', { name: 'Send to My Agent Securely' }));

    const prompt = await screen.findByTestId('agent-prompt');
    expect(createShare).toHaveBeenCalledWith(KEY);
    expect(prompt.textContent).toContain(LINK);
    expect(prompt.textContent).not.toContain(KEY);
    expect(screen.getByRole('button', { name: 'Copy Prompt' })).toBeTruthy();
    expect(document.body.textContent).not.toContain(KEY);
  });

  it('offers the key behind a warning, and after a failed link', async () => {
    renderHandoff(vi.fn(async () => Promise.reject(new Error('offline'))));
    fireEvent.click(screen.getByRole('button', { name: 'Send to My Agent Securely' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      "Couldn't create the secure link",
    );

    fireEvent.click(screen.getByRole('button', { name: 'Show the key instead' }));
    expect(screen.getByText(KEY)).toBeTruthy();
    expect(screen.getByText(/Anyone with this key can read your Omi data/)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Copy Key' })).toBeTruthy();
  });
});

describe('developerRedirectTarget', () => {
  it('sends retired Settings → Developer links to /developers with their anchor', () => {
    expect(developerRedirectTarget('developer', '')).toBe('/developers');
    expect(developerRedirectTarget('developer', '#mcp')).toBe('/developers#mcp');
    expect(developerRedirectTarget('account', '#mcp')).toBeNull();
    expect(developerRedirectTarget(null, '')).toBeNull();
  });
});
