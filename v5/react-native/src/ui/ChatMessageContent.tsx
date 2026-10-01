import React, {useMemo} from 'react';
import {
  Alert,
  Linking,
  StyleSheet,
  Text,
  View,
  type TextStyle,
  type ViewStyle,
} from 'react-native';
import {Renderer, useMarkdown, type MarkedStyles} from 'react-native-marked';
import type {ChatMessageContentProps} from './ChatMessageContent.types';
import {useOmiTheme} from '../design/OmiTheme';
import {ChatCodeBlock, chatMonospace} from './ChatCodeBlock';

class ChatMarkdownRenderer extends Renderer {
  constructor(private readonly base: TextStyle) {
    super();
  }
  link(children: string | React.ReactNode[], href: string, style?: TextStyle) {
    // React Native's URL implementation lacks protocol/credential getters.
    const authority = /^https?:\/\/([^/?#]+)(?:[/?#]|$)/i.exec(href)?.[1];
    const safe =
      authority !== undefined &&
      !/[\s\u0000-\u001f\u007f\\]/.test(href) &&
      !authority.includes('@');
    return (
      <Text
        key={this.getKey()}
        selectable
        style={style}
        accessibilityRole={safe ? 'link' : undefined}
        onPress={
          safe
            ? () => {
                Linking.openURL(href).catch(() => {
                  Alert.alert('Could not open link', 'Please try again.');
                });
              }
            : undefined
        }>
        {children}
      </Text>
    );
  }

  // Fenced code gets a language label, a Copy button and a horizontal
  // scroll (ChatCodeBlock) instead of the library's bare scroll view.
  code(
    text: string,
    language?: string,
    _containerStyle?: ViewStyle,
    _textStyle?: TextStyle,
  ) {
    return (
      <ChatCodeBlock key={this.getKey()} code={text} language={language} />
    );
  }

  // Model-authored image URLs must never trigger background network requests.
  image(_uri: string, alt?: string) {
    return this.text(alt || '[Image]', this.base);
  }

  linkImage(href: string, _imageUrl: string, alt?: string) {
    return this.link(alt || '[Image]', href, this.base);
  }
}

function MarkdownChatMessageContent({
  text,
  style,
}: Pick<ChatMessageContentProps, 'text' | 'style'>) {
  const theme = useOmiTheme();
  const renderer = useMemo(
    () => new ChatMarkdownRenderer(StyleSheet.flatten(style) || {}),
    [style],
  );
  const styles = useMemo<MarkedStyles>(() => {
    const base = StyleSheet.flatten(style) || {};
    const heading = {...base, fontWeight: '600' as const};
    return {
      text: base,
      li: base,
      strikethrough: {...base, textDecorationLine: 'line-through'},
      strong: {...base, fontWeight: '700'},
      em: {...base, fontStyle: 'italic'},
      link: {...base, color: theme.color.link, textDecorationLine: 'underline'},
      h1: {...heading, fontSize: (base.fontSize ?? 15) + 4},
      h2: {...heading, fontSize: (base.fontSize ?? 15) + 2},
      h3: heading,
      h4: heading,
      h5: heading,
      h6: heading,
      codespan: {
        ...base,
        fontFamily: chatMonospace,
        fontSize: (base.fontSize ?? 15) - 1,
        backgroundColor: theme.color.fillSelected,
      },
      paragraph: {marginTop: 0, marginBottom: 8},
      blockquote: {
        borderLeftColor: theme.color.hairline,
        borderLeftWidth: 2,
        paddingLeft: theme.space.md,
      },
      table: {borderColor: theme.color.hairline},
      hr: {backgroundColor: theme.color.separator, height: 1},
    };
  }, [style, theme]);
  const elements = useMarkdown(text, {renderer, styles});
  return <View>{elements}</View>;
}

export function ChatMessageContent({
  text,
  style,
  streaming,
}: ChatMessageContentProps) {
  if (streaming) {
    return (
      <Text selectable style={style}>
        {text}
      </Text>
    );
  }
  return <MarkdownChatMessageContent text={text} style={style} />;
}
