import React, {useState} from 'react';
import {Text, TextInput, View} from 'react-native';
import type {MemoryProjection} from '../desktopReadClient';
import {
  deleteMemory,
  editMemory,
  setMemoryVisibility,
} from '../legacyOmiWrites';
import {omiBackend} from '../omiNative';
import {FocusPressable} from '../ui/Pressable';

export function MemoryWriteActions({
  memory,
  writesAvailable,
  onRefresh,
  onDeleted,
}: {
  memory: MemoryProjection;
  writesAvailable: boolean;
  onRefresh: () => Promise<void>;
  onDeleted?: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [content, setContent] = useState(memory.summary);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const refreshAfter = async () => {
    try {
      await onRefresh();
      setMessage(null);
      return true;
    } catch {
      setMessage('Saved, but memories could not be refreshed.');
      return false;
    }
  };
  const save = async () => {
    if (omiBackend == null || content.trim() === '') return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await editMemory(omiBackend, memory.id, content);
      if (!result.ok) {
        setMessage(result.failure.detail);
        return;
      }
      await refreshAfter();
      setEditing(false);
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (omiBackend == null) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await deleteMemory(omiBackend, memory.id);
      if (!result.ok) {
        setMessage(result.failure.detail);
        return;
      }
      await refreshAfter();
      setConfirmingDelete(false);
      onDeleted?.();
    } finally {
      setBusy(false);
    }
  };
  const toggleVisibility = async () => {
    if (omiBackend == null) return;
    setBusy(true);
    setMessage(null);
    try {
      const visibility = memory.visibility === 'public' ? 'private' : 'public';
      const result = await setMemoryVisibility(
        omiBackend,
        memory.id,
        visibility,
      );
      if (!result.ok) {
        setMessage(result.failure.detail);
        return;
      }
      await refreshAfter();
    } finally {
      setBusy(false);
    }
  };

  if (!writesAvailable) return null;
  return (
    <View accessibilityLabel="Memory actions" style={{gap: 8, marginTop: 12}}>
      {editing ? (
        <>
          <TextInput
            accessibilityLabel="Edit memory content"
            multiline
            onChangeText={setContent}
            style={{minHeight: 80, padding: 8, borderWidth: 1}}
            value={content}
          />
          <View style={{flexDirection: 'row', gap: 8}}>
            <FocusPressable
              accessibilityRole="button"
              accessibilityLabel="Save memory"
              disabled={busy || content.trim() === ''}
              onPress={() => void save()}>
              <Text>Save</Text>
            </FocusPressable>
            <FocusPressable
              accessibilityRole="button"
              accessibilityLabel="Cancel memory edit"
              disabled={busy}
              onPress={() => {
                setContent(memory.summary);
                setEditing(false);
              }}>
              <Text>Cancel</Text>
            </FocusPressable>
          </View>
        </>
      ) : (
        <View style={{flexDirection: 'row', flexWrap: 'wrap', gap: 8}}>
          <FocusPressable
            accessibilityRole="button"
            accessibilityLabel="Edit memory"
            disabled={busy}
            onPress={() => {
              setContent(memory.summary);
              setEditing(true);
            }}>
            <Text>Edit</Text>
          </FocusPressable>
          <FocusPressable
            accessibilityRole="button"
            accessibilityLabel={`Make memory ${
              memory.visibility === 'public' ? 'private' : 'public'
            }`}
            disabled={busy}
            onPress={() => void toggleVisibility()}>
            <Text>
              {memory.visibility === 'public' ? 'Make private' : 'Make public'}
            </Text>
          </FocusPressable>
          <FocusPressable
            accessibilityRole="button"
            accessibilityLabel="Delete memory"
            disabled={busy}
            onPress={() => setConfirmingDelete(true)}>
            <Text>Delete</Text>
          </FocusPressable>
        </View>
      )}
      {confirmingDelete ? (
        <View accessibilityLabel="Confirm memory deletion" style={{gap: 8}}>
          <Text>Delete this memory?</Text>
          <View style={{flexDirection: 'row', gap: 8}}>
            <FocusPressable
              accessibilityRole="button"
              accessibilityLabel="Confirm delete memory"
              disabled={busy}
              onPress={() => void remove()}>
              <Text>Confirm delete</Text>
            </FocusPressable>
            <FocusPressable
              accessibilityRole="button"
              accessibilityLabel="Cancel delete memory"
              disabled={busy}
              onPress={() => setConfirmingDelete(false)}>
              <Text>Cancel</Text>
            </FocusPressable>
          </View>
        </View>
      ) : null}
      {message ? <Text accessibilityRole="alert">{message}</Text> : null}
    </View>
  );
}
