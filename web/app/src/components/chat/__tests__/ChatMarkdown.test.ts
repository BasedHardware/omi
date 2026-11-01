import { createElement } from 'react';
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ChatMarkdown } from '@/components/chat/ChatMarkdown';
import { Streamdown } from 'streamdown';

vi.mock('streamdown', async (importOriginal) => ({
  ...(await importOriginal<typeof import('streamdown')>()),
  Streamdown: vi.fn(() => null),
}));

// Mount through React now that message-local citation navigation uses hooks.
describe('ChatMarkdown', () => {
  it('uses Streamdown for completed assistant responses', () => {
    render(
      createElement(ChatMarkdown, { children: '## Next steps\n\n- **Ship** the update' }),
    );
    expect(Streamdown).toHaveBeenCalled();
    const props = vi.mocked(Streamdown).mock.lastCall![0];
    expect(props.mode).toBe('static');
    expect(props.children).toBe('## Next steps\n\n- **Ship** the update');
  });

  it('enables incomplete Markdown parsing while a response streams', () => {
    render(
      createElement(ChatMarkdown, { children: '**Still writing', isStreaming: true }),
    );
    const props = vi.mocked(Streamdown).mock.lastCall![0];
    expect(props.mode).toBe('streaming');
    expect(props.isAnimating).toBe(true);
    expect(props.parseIncompleteMarkdown).toBe(true);
    expect(props.caret).toBe('block');
  });
});
