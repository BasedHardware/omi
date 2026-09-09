import React, {useMemo} from 'react';
import {
  Alert,
  Linking,
  Platform,
  StyleSheet,
  Text,
  View,
  type TextStyle,
  type ViewStyle,
} from 'react-native';
import {Renderer, useMarkdown, type MarkedStyles} from 'react-native-marked';
import type {ChatMessageContentProps} from './ChatMessageContent.types';

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

  code(
    text: string,
    language?: string,
    containerStyle?: ViewStyle,
    textStyle?: TextStyle,
  ) {
    return super.code(text, language, containerStyle, {
      ...textStyle,
      fontStyle: 'normal',
      fontFamily:
        Platform.OS === 'ios' || Platform.OS === 'macos'
          ? 'Menlo'
          : 'monospace',
    });
  }

  // Model-authored image URLs must never trigger background network requests.
  image(_uri: string, alt?: string) {
    return this.text(alt || '[Image]', this.base);
  }

  linkImage(href: string, _imageUrl: string, alt?: string) {
    return this.link(alt || '[Image]', href, this.base);
  }
}

export function ChatMessageContent({text, style}: ChatMessageContentProps) {
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
      link: {...base, textDecorationLine: 'underline'},
      h1: heading,
      h2: heading,
      h3: heading,
      h4: heading,
      h5: heading,
      h6: heading,
      codespan: {
        ...base,
        fontFamily:
          Platform.OS === 'ios' || Platform.OS === 'macos'
            ? 'Menlo'
            : 'monospace',
        backgroundColor: 'transparent',
      },
      code: {backgroundColor: 'transparent', padding: 8},
      paragraph: {marginTop: 0, marginBottom: 8},
      blockquote: {
        borderLeftColor: '#8a8a8a',
        borderLeftWidth: 2,
        paddingLeft: 12,
      },
      table: {borderColor: '#8a8a8a'},
    };
  }, [style]);
  const elements = useMarkdown(text, {renderer, styles});
  return <View>{elements}</View>;
}
