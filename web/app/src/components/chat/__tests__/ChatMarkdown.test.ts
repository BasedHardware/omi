import { describe, expect, it } from 'vitest';
import { ChatMarkdown } from '@/components/chat/ChatMarkdown';
import { Streamdown } from 'streamdown';

describe('ChatMarkdown', () => {
  it('uses Streamdown for completed assistant responses', () => {
    const element = ChatMarkdown({ children: '## Next steps\n\n- **Ship** the update' });

    expect(element.type).toBe(Streamdown);
    expect(element.props.mode).toBe('static');
    expect(element.props.children).toBe('## Next steps\n\n- **Ship** the update');
  });

  it('enables incomplete Markdown parsing while a response streams', () => {
    const element = ChatMarkdown({ children: '**Still writing', isStreaming: true });

    expect(element.props.mode).toBe('streaming');
    expect(element.props.isAnimating).toBe(true);
    expect(element.props.parseIncompleteMarkdown).toBe(true);
    expect(element.props.caret).toBe('block');
  });
});
