import React from 'react';
import {Platform, Text, View} from 'react-native';
import {FocusPressable} from './Pressable';
import {styles} from './styles';

export function TaskPagination({
  hasMore,
  busy,
  notice,
  onLoadMore,
}: {
  hasMore: boolean;
  busy: boolean;
  notice: string | null;
  onLoadMore: () => void;
}) {
  const textStyle = [
    styles.projectionEmptyCopy,
    Platform.OS === 'macos' && styles.macPrimaryText,
  ];
  return (
    <View>
      {notice && (
        <Text accessibilityRole="alert" style={textStyle}>
          {notice}
        </Text>
      )}
      {hasMore && (
        <FocusPressable
          accessibilityRole="button"
          accessibilityLabel="Load more tasks"
          accessibilityState={{disabled: busy}}
          disabled={busy}
          onPress={onLoadMore}
          style={{minHeight: 44, justifyContent: 'center'}}>
          <Text style={textStyle}>{busy ? 'Loading…' : 'Load more tasks'}</Text>
        </FocusPressable>
      )}
    </View>
  );
}
