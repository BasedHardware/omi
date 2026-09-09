import {FocusPressable as Pressable} from './Pressable';
import React, {useEffect, useRef, useState} from 'react';
import {Platform, StyleSheet, Text, TextInput, View} from 'react-native';
import {visibleDisplayText} from '../desktopReadClient';

export type TaskMutationProps = {
  onTaskToggle?: (id: string) => void;
  onTaskEdit?: (id: string, description: string) => void;
  busyTaskId?: string | null;
  taskMutationError?: string | null;
  onRetryTaskMutation?: () => void;
  onDismissTaskMutation?: () => void;
  writesAvailable?: boolean | null;
};

export function TaskMutationStatus({
  writesAvailable,
  taskMutationError,
  onRetryTaskMutation,
  onDismissTaskMutation,
}: TaskMutationProps) {
  return (
    <View>
      {writesAvailable === false && (
        <Text
          style={[styles.copy, Platform.OS === 'macos' && styles.lightText]}>
          Task editing is unavailable for this connection.
        </Text>
      )}
      {taskMutationError && (
        <Text
          accessibilityRole="alert"
          style={[styles.copy, Platform.OS === 'macos' && styles.lightText]}>
          {taskMutationError}
        </Text>
      )}
      {taskMutationError && onRetryTaskMutation && writesAvailable && (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Retry task change"
          onPress={onRetryTaskMutation}
          style={styles.button}>
          <Text
            style={[styles.label, Platform.OS === 'macos' && styles.lightText]}>
            Retry
          </Text>
        </Pressable>
      )}
      {taskMutationError && onDismissTaskMutation && (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Dismiss task change"
          onPress={onDismissTaskMutation}
          style={styles.button}>
          <Text
            style={[styles.label, Platform.OS === 'macos' && styles.lightText]}>
            Dismiss
          </Text>
        </Pressable>
      )}
    </View>
  );
}

export function TaskEditor({
  id,
  title,
  busy,
  failed = false,
  onSave,
  onClose,
}: {
  id: string;
  title: string;
  busy: boolean;
  failed?: boolean;
  onSave: (id: string, description: string) => void;
  onClose: () => void;
}) {
  const [description, setDescription] = useState(title);
  const previousTask = useRef({id, title});
  useEffect(() => {
    const previous = previousTask.current;
    previousTask.current = {id, title};
    setDescription(current =>
      previous.id !== id || current === previous.title ? title : current,
    );
  }, [id, title]);
  const disabled =
    busy ||
    visibleDisplayText(description).length === 0 ||
    description === title;
  return (
    <View style={styles.editor}>
      <TextInput
        accessibilityLabel="Task description"
        editable={!busy}
        multiline
        onChangeText={setDescription}
        value={description}
        style={[styles.input, Platform.OS === 'macos' && styles.lightInput]}
      />
      <View style={styles.actions}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Save task description"
          accessibilityState={{disabled, busy: busy && !failed}}
          disabled={disabled}
          onPress={() => onSave(id, description)}
          style={styles.button}>
          <Text
            style={[
              styles.label,
              Platform.OS === 'macos' && styles.lightText,
              disabled && styles.disabled,
            ]}>
            {busy && !failed ? 'Saving…' : 'Save'}
          </Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Close task editor"
          onPress={onClose}
          style={styles.button}>
          <Text
            style={[styles.label, Platform.OS === 'macos' && styles.lightText]}>
            Close
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  lightText: {color: '#292929'},
  lightInput: {backgroundColor: '#ffffff', color: '#292929'},
  editor: {paddingVertical: 12, gap: 8},
  input: {
    borderColor: '#b9b9b9',
    borderWidth: 1,
    borderRadius: 12,
    color: '#ffffff',
    backgroundColor: '#1f1f25',
    padding: 12,
    minHeight: 64,
    textAlignVertical: 'top',
  },
  actions: {flexDirection: 'row', flexWrap: 'wrap', gap: 8},
  button: {
    minHeight: 44,
    minWidth: 44,
    paddingHorizontal: 12,
    justifyContent: 'center',
  },
  label: {color: '#ffffff', fontSize: 14, fontWeight: '600'},
  copy: {color: '#a1a1a1', fontSize: 13, lineHeight: 19, paddingVertical: 8},
  disabled: {opacity: 0.45},
});
