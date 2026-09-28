import React, {useEffect, useRef, useState} from 'react';
import {Platform, ScrollView, Text, View, type TextStyle} from 'react-native';
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import type {OmiTheme} from '../design/tokens';
import {MaterialIcon} from './MaterialIcon';
import {FocusPressable} from './Pressable';
import {chatCopySharesOnPhone, copyChatText} from './chatClipboard';

export const chatMonospace =
  Platform.OS === 'ios' || Platform.OS === 'macos' ? 'Menlo' : 'monospace';

/**
 * A fenced code block in an Omi reply: a quiet header with the language and
 * a Copy button, and the code on one horizontal scroll so long lines never
 * wrap mid-token.
 */
export function ChatCodeBlock({
  code,
  language,
  textStyle,
  onCopy = copyChatText,
}: {
  code: string;
  language?: string;
  textStyle?: TextStyle;
  onCopy?: (text: string) => Promise<unknown>;
}) {
  const theme = useOmiTheme();
  const styles = useOmiStyles(createStyles);
  const [state, setState] = useState<'ready' | 'copied' | 'failed'>('ready');
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (timer.current !== null) {
        clearTimeout(timer.current);
      }
    },
    [],
  );
  const label =
    state === 'copied'
      ? 'Copied'
      : state === 'failed'
      ? 'Copy unavailable'
      : chatCopySharesOnPhone()
      ? 'Share or copy code'
      : 'Copy code';
  return (
    <View style={styles.block} accessibilityLabel="Code block">
      <View style={styles.header}>
        <Text style={styles.language}>{language?.trim() || 'Code'}</Text>
        <FocusPressable
          accessibilityRole="button"
          accessibilityLabel={label}
          {...({tooltip: label, title: label} as object)}
          onPress={() => {
            onCopy(code)
              .then(result => {
                if (result === 'dismissed') {
                  return;
                }
                setState('copied');
                if (timer.current !== null) {
                  clearTimeout(timer.current);
                }
                timer.current = setTimeout(() => setState('ready'), 1600);
              })
              .catch(() => setState('failed'));
          }}
          style={press => [
            styles.copy,
            (press as {hovered?: boolean}).hovered && styles.copyHovered,
          ]}>
          <MaterialIcon
            name={state === 'copied' ? 'check' : 'content_copy'}
            size={13}
            color={theme.color.inkSecondary}
          />
          <Text style={styles.copyText}>
            {state === 'copied' ? 'Copied' : 'Copy'}
          </Text>
        </FocusPressable>
      </View>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator
        contentContainerStyle={styles.scroll}>
        <Text selectable style={[textStyle, styles.code]}>
          {code}
        </Text>
      </ScrollView>
    </View>
  );
}

const createStyles = (t: OmiTheme) => ({
  block: {
    marginVertical: t.space.xs,
    borderRadius: t.radius.row,
    borderWidth: 1,
    borderColor: t.color.separator,
    backgroundColor: t.color.fill,
    overflow: 'hidden' as const,
  },
  header: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    justifyContent: 'space-between' as const,
    paddingLeft: t.space.md,
    paddingRight: t.space.xs,
    paddingVertical: 2,
    borderBottomWidth: 1,
    borderBottomColor: t.color.separator,
  },
  language: {...t.type.caption, color: t.color.inkSecondary},
  copy: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: t.space.xs,
    minHeight: t.density === 'desktop' ? 24 : 36,
    paddingHorizontal: t.space.sm,
    borderRadius: t.radius.pill,
  },
  copyHovered: {backgroundColor: t.color.fill},
  copyText: {...t.type.caption, color: t.color.inkSecondary},
  scroll: {padding: t.space.md},
  code: {
    ...t.type.subhead,
    fontFamily: chatMonospace,
    fontStyle: 'normal' as const,
    fontWeight: '400' as const,
    color: t.color.ink,
  },
});
