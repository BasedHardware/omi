import React from 'react';
import {
  AccessibilityInfo,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
} from 'react-native';
import Renderer, {act} from 'react-test-renderer';
import type {ChatMessage} from '../chatClient';
import {ChatCodeBlock} from './ChatCodeBlock';
import {ChatComposer, CHAT_COMPOSER_MAX_LINES} from './ChatComposer';
import {ChatMessageContent} from './ChatMessageContent';
import {ChatThread} from './ChatThread';
import {ChatDaySeparator, ChatMessageRow} from './ChatTranscript';
import {buildChatTimeline, chatDayLabel} from './chatTimeline';
import {omiType} from '../design/tokens';

jest.mock('../app/useReduceMotion', () => ({useReduceMotion: () => true}));
jest.mock('../omiNative', () => ({omiBackend: {}}));

const human = (id: string, text: string, createdAt: number): ChatMessage => ({
  id,
  sender: 'human',
  text,
  createdAt,
  generationOutcome: null,
});
const reply = (
  id: string,
  text: string,
  createdAt: number,
  outcome: ChatMessage['generationOutcome'] = 'completed',
): ChatMessage => ({
  id,
  sender: 'ai',
  text,
  createdAt,
  generationOutcome: outcome,
  generationId: id,
  generationRetryable: outcome === 'failed',
});

function withPlatform<T>(os: string, run: () => T): T {
  const previous = Platform.OS;
  Object.defineProperty(Platform, 'OS', {configurable: true, value: os});
  try {
    return run();
  } finally {
    Object.defineProperty(Platform, 'OS', {
      configurable: true,
      value: previous,
    });
  }
}

const labelled = (tree: Renderer.ReactTestRenderer, label: string) =>
  tree.root.findAll(node => node.props.accessibilityLabel === label);

describe('transcript layout', () => {
  // Wed Sep 23 2026, 15:00 local.
  const now = new Date(2026, 8, 23, 15, 0).getTime();
  const at = (day: number, hour: number, minute = 0) =>
    new Date(2026, 8, day, hour, minute).getTime();

  test('day separators read Today, Yesterday, then a short date', () => {
    expect(chatDayLabel(at(23, 9), now)).toBe('Today');
    expect(chatDayLabel(at(22, 23, 59), now)).toBe('Yesterday');
    expect(chatDayLabel(at(21, 10), now)).toMatch(/Mon.*Sep.*21/);
    expect(chatDayLabel(new Date(2025, 0, 2).getTime(), now)).toMatch(/2025/);
  });

  test('turns group tightly by sender within five minutes and restart each day', () => {
    const items = buildChatTimeline(
      [
        human('h1', 'One', at(22, 10)),
        human('h2', 'Two', at(22, 10, 2)),
        reply('a1', 'Answer', at(22, 10, 3)),
        human('h3', 'Later', at(22, 10, 30)),
        human('h4', 'Next day', at(23, 9)),
        reply('a2', 'Newest', at(23, 9, 1)),
      ],
      now,
    );
    expect(
      items.map(item =>
        item.kind === 'day'
          ? `[${item.label}]`
          : `${item.message.id}${item.grouped ? '+' : ''}${
              item.latestReply ? '*' : ''
            }`,
      ),
    ).toEqual(['[Yesterday]', 'h1', 'h2+', 'a1', 'h3', '[Today]', 'h4', 'a2*']);
  });

  test('the thread renders day headers instead of per-message timestamps', () => {
    let tree!: Renderer.ReactTestRenderer;
    act(() => {
      tree = Renderer.create(
        <ChatThread
          messages={[
            human('h1', 'Hello', Date.now() - 24 * 60 * 60 * 1000),
            reply('a1', 'Hi there', Date.now()),
          ]}
          busy={false}
          desktop
          hasOlder={false}
          loadingOlder={false}
          onLoadOlder={jest.fn()}
          reduceMotion
        />,
      );
    });
    expect(
      tree.root.findAllByType(ChatDaySeparator).map(node => node.props.label),
    ).toEqual(['Yesterday', 'Today']);
    const texts = tree.root
      .findAllByType(Text)
      .map(node => String(node.props.children));
    expect(texts.some(text => /\d{1,2}:\d{2}/.test(text))).toBe(false);
    // The time is still available: tooltip and accessibility hint.
    expect(
      tree.root.findAll(node =>
        String(node.props.accessibilityHint).startsWith('Sent at'),
      ).length,
    ).toBeGreaterThan(0);
    act(() => tree.unmount());
  });
});

describe('reply actions', () => {
  test('desktop: the latest reply keeps its bar; older ones show it on hover or focus', () => {
    withPlatform('macos', () => {
      let tree!: Renderer.ReactTestRenderer;
      const render = (latest: boolean) => (
        <ChatMessageRow
          message={reply('a1', 'An answer', 1000)}
          animate={false}
          compact={false}
          desktop
          latest={latest}
          reduceMotion
        />
      );
      act(() => {
        tree = Renderer.create(render(false));
      });
      const bar = () =>
        StyleSheet.flatten(labelled(tree, 'Response actions')[0].props.style);
      expect(bar().opacity).toBe(0);
      const row = tree.root.find(
        node => typeof node.props.onMouseEnter === 'function',
      );
      act(() => row.props.onMouseEnter());
      expect(bar().opacity).toBeUndefined();
      act(() => row.props.onMouseLeave());
      expect(bar().opacity).toBe(0);
      act(() => labelled(tree, 'Copy response')[0].props.onFocus());
      expect(bar().opacity).toBeUndefined();
      act(() => labelled(tree, 'Copy response')[0].props.onBlur());
      expect(bar().opacity).toBe(0);
      act(() => tree.update(render(true)));
      expect(bar().opacity).toBeUndefined();
      act(() => tree.unmount());
    });
  });

  test('a failed retryable reply offers Try Again inline; streaming replies have no bar', () => {
    const onRetry = jest.fn();
    let tree!: Renderer.ReactTestRenderer;
    act(() => {
      tree = Renderer.create(
        <ChatMessageRow
          message={reply('a1', '', 1000, 'failed')}
          animate={false}
          compact={false}
          desktop
          latest
          reduceMotion
          onRetry={onRetry}
        />,
      );
    });
    act(() => labelled(tree, 'Try Again')[0].props.onPress());
    expect(onRetry).toHaveBeenCalledTimes(1);
    act(() =>
      tree.update(
        <ChatMessageRow
          message={{...reply('a1', 'Partial', 1000, null)}}
          animate={false}
          compact={false}
          desktop
          latest
          reduceMotion
        />,
      ),
    );
    expect(labelled(tree, 'Response actions')).toHaveLength(0);
    act(() => tree.unmount());
  });
});

describe('composer', () => {
  function renderComposer(
    overrides: Partial<React.ComponentProps<typeof ChatComposer>> = {},
  ) {
    const props: React.ComponentProps<typeof ChatComposer> = {
      value: 'Hello',
      onChangeText: jest.fn(),
      onSend: jest.fn(),
      onStop: jest.fn(),
      canStop: false,
      busy: false,
      ...overrides,
    };
    let tree!: Renderer.ReactTestRenderer;
    act(() => {
      tree = Renderer.create(<ChatComposer {...props} />);
    });
    return {tree, props, input: () => tree.root.findByType(TextInput)};
  }

  test('Enter sends, Shift+Enter and IME composition do not', () => {
    const {tree, props, input} = renderComposer();
    const preventDefault = jest.fn();
    act(() =>
      input().props.onKeyPress({
        nativeEvent: {key: 'Enter', shiftKey: true},
        preventDefault,
      }),
    );
    act(() =>
      input().props.onKeyPress({
        nativeEvent: {key: 'Enter', isComposing: true},
        preventDefault,
      }),
    );
    expect(props.onSend).not.toHaveBeenCalled();
    expect(preventDefault).not.toHaveBeenCalled();
    act(() =>
      input().props.onKeyPress({nativeEvent: {key: 'Enter'}, preventDefault}),
    );
    expect(props.onSend).toHaveBeenCalledTimes(1);
    expect(preventDefault).toHaveBeenCalledTimes(1);
    expect(input().props.multiline).toBe(true);
    act(() => tree.unmount());
  });

  test('macOS hands plain Enter to JS so it sends without inserting a line', () => {
    withPlatform('macos', () => {
      const {tree, props, input} = renderComposer();
      expect(input().props.keyDownEvents).toEqual([{key: 'Enter'}]);
      act(() => input().props.onKeyDown({nativeEvent: {key: 'Enter'}}));
      expect(props.onSend).toHaveBeenCalledTimes(1);
      act(() => tree.unmount());
    });
  });

  test('Esc leaves the field; an empty or pending draft cannot send', () => {
    const blur = jest.fn();
    const {tree, props, input} = renderComposer({value: '   '});
    act(() =>
      input().props.onKeyPress({
        nativeEvent: {key: 'Escape'},
        currentTarget: {blur},
      }),
    );
    expect(blur).toHaveBeenCalled();
    act(() => input().props.onKeyPress({nativeEvent: {key: 'Enter'}}));
    act(() => labelled(tree, 'Send')[0].props.onPress());
    expect(props.onSend).not.toHaveBeenCalled();
    act(() =>
      tree.update(
        <ChatComposer {...props} value="Ready" busy canStop={false} />,
      ),
    );
    expect(labelled(tree, 'Send')[0].props.disabled).toBe(true);
    act(() => tree.unmount());
  });

  test('the send circle becomes Stop while Omi answers', () => {
    const {tree, props} = renderComposer({canStop: true, busy: true});
    expect(labelled(tree, 'Send')).toHaveLength(0);
    act(() => labelled(tree, 'Stop')[0].props.onPress());
    expect(props.onStop).toHaveBeenCalledTimes(1);
    expect(props.onSend).not.toHaveBeenCalled();
    act(() => tree.unmount());
  });

  test('the field grows with the draft up to eight lines, then scrolls', () => {
    const {tree, props, input} = renderComposer();
    const height = () => StyleSheet.flatten(input().props.style).height;
    const start = height();
    const line = omiType.mobile.body.lineHeight;
    act(() =>
      input().props.onContentSizeChange({
        nativeEvent: {contentSize: {height: start + line * 2}},
      }),
    );
    expect(height()).toBe(start + line * 2);
    expect(input().props.scrollEnabled).toBe(false);
    act(() =>
      input().props.onContentSizeChange({
        nativeEvent: {contentSize: {height: 4000}},
      }),
    );
    expect(height()).toBe(start + line * (CHAT_COMPOSER_MAX_LINES - 1));
    expect(input().props.scrollEnabled).toBe(true);
    act(() => tree.update(<ChatComposer {...props} value="" />));
    expect(height()).toBe(start);
    act(() => tree.unmount());
  });
});

describe('code blocks', () => {
  test('fenced code shows its language and copies the exact code', async () => {
    const onCopy = jest.fn(async () => 'copied' as const);
    let tree!: Renderer.ReactTestRenderer;
    act(() => {
      tree = Renderer.create(
        <ChatCodeBlock
          code={'echo hi\nls -la'}
          language="sh"
          onCopy={onCopy}
        />,
      );
    });
    expect(
      tree.root.findAllByType(Text).map(node => node.props.children),
    ).toContain('sh');
    // Long lines scroll sideways instead of wrapping.
    expect(tree.root.findByType(ScrollView).props.horizontal).toBe(true);
    await act(async () =>
      labelled(tree, 'Share or copy code')[0].props.onPress(),
    );
    expect(onCopy).toHaveBeenCalledWith('echo hi\nls -la');
    expect(labelled(tree, 'Copied').length).toBeGreaterThan(0);
    act(() => tree.unmount());
  });

  test('native Markdown renders fenced code through the code block', () => {
    let tree!: Renderer.ReactTestRenderer;
    act(() => {
      tree = Renderer.create(
        <ChatMessageContent text={'Run:\n\n```js\nconst a = 1;\n```'} />,
      );
    });
    const block = tree.root.findByType(ChatCodeBlock);
    expect(block.props).toMatchObject({code: 'const a = 1;', language: 'js'});
    act(() => tree.unmount());
  });
});

describe('stick to bottom', () => {
  const scrolledAway = {
    nativeEvent: {
      contentOffset: {y: 0},
      contentSize: {height: 2000},
      layoutMeasurement: {height: 400},
    },
  };

  test('sending a new message resumes following and hides Jump to Latest', () => {
    const scrollToEnd = jest
      .spyOn(ScrollView.prototype, 'scrollToEnd')
      .mockImplementation(() => undefined);
    try {
      const base = [human('h1', 'Hi', 1000), reply('a1', 'Hello', 1001)];
      const props = {
        busy: false,
        desktop: false,
        hasOlder: false,
        loadingOlder: false,
        onLoadOlder: jest.fn(),
        reduceMotion: true,
      };
      let tree!: Renderer.ReactTestRenderer;
      act(() => {
        tree = Renderer.create(<ChatThread {...props} messages={base} />);
      });
      const scroll = () => tree.root.findByType(ScrollView);
      act(() => {
        scroll().props.onScrollBeginDrag();
        scroll().props.onScroll(scrolledAway);
      });
      expect(labelled(tree, 'Jump to Latest').length).toBeGreaterThan(0);
      scrollToEnd.mockClear();
      // A passive update (Omi still writing) does not yank the reader down.
      act(() =>
        tree.update(
          <ChatThread
            {...props}
            messages={[...base, reply('a2', 'More', 1002, null)]}
          />,
        ),
      );
      act(() => scroll().props.onContentSizeChange(600, 2400));
      expect(scrollToEnd).not.toHaveBeenCalled();
      // Sending (a new local message) does.
      act(() =>
        tree.update(
          <ChatThread
            {...props}
            busy
            messages={[
              ...base,
              {...human('local', 'Follow up', 1003), localOnly: true},
            ]}
          />,
        ),
      );
      expect(scrollToEnd).toHaveBeenCalledWith({animated: false});
      expect(labelled(tree, 'Jump to Latest')).toHaveLength(0);
      act(() => tree.unmount());
    } finally {
      scrollToEnd.mockRestore();
    }
  });

  test('screen readers hear when a reply finishes', () => {
    const announce = jest
      .spyOn(AccessibilityInfo, 'announceForAccessibility')
      .mockImplementation(() => undefined);
    // The React Native preset already mocks this; start from a clean count.
    announce.mockClear();
    try {
      const props = {
        busy: true,
        desktop: true,
        hasOlder: false,
        loadingOlder: false,
        onLoadOlder: jest.fn(),
        reduceMotion: true,
      };
      const question = human('h1', 'Hi', 1000);
      let tree!: Renderer.ReactTestRenderer;
      act(() => {
        tree = Renderer.create(
          <ChatThread
            {...props}
            messages={[question, reply('a1', 'Hel', 1001, null)]}
          />,
        );
      });
      expect(announce).not.toHaveBeenCalled();
      act(() =>
        tree.update(
          <ChatThread
            {...props}
            busy={false}
            messages={[question, reply('a1', 'Hello', 1001)]}
          />,
        ),
      );
      expect(announce).toHaveBeenCalledWith('Omi replied');
      act(() => tree.unmount());
    } finally {
      announce.mockRestore();
    }
  });
});
