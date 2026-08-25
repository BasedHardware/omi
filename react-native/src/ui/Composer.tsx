import React from 'react';
import {TextInput, View} from 'react-native';
import ArrowUp from 'lucide-react-native/icons/arrow-up';
import Mic from 'lucide-react-native/icons/mic';
import Paperclip from 'lucide-react-native/icons/paperclip';
import Square from 'lucide-react-native/icons/square';
import {omiBackend} from '../omiNative';
import {FocusPressable} from './Pressable';
import {styles} from './styles';

export function Composer({
  activeGenerationId,
  chatBusy,
  compact,
  composerFocused,
  composerMaxWidth,
  composerRef,
  draft,
  onDraftChange,
  onFocusChange,
  onSend,
  onStop,
}: {
  activeGenerationId: string | null;
  chatBusy: boolean;
  compact: boolean;
  composerFocused: boolean;
  composerMaxWidth: number;
  composerRef: React.RefObject<TextInput | null>;
  draft: string;
  onDraftChange: (value: string) => void;
  onFocusChange: (focused: boolean) => void;
  onSend: () => void;
  onStop: () => void;
}) {
  return (
    <View style={[styles.composerWrap, compact && styles.composerWrapCompact]}>
      <View
        style={[
          styles.composer,
          composerFocused && styles.composerFocused,
          {maxWidth: composerMaxWidth},
        ]}>
        <TextInput
          accessibilityLabel="Ask Omi"
          multiline
          onBlur={() => onFocusChange(false)}
          onChangeText={onDraftChange}
          onFocus={() => onFocusChange(true)}
          placeholder="Ask anything..."
          placeholderTextColor="#888888"
          ref={composerRef}
          style={styles.composerInput}
          value={draft}
        />
        <View style={styles.composerActions}>
          <FocusPressable
            accessibilityLabel="Attach file unavailable"
            accessibilityRole="button"
            disabled
            style={({pressed}) => [
              styles.iconButton,
              pressed && styles.pressed,
            ]}>
            <Paperclip color="#666666" size={18} strokeWidth={2} />
          </FocusPressable>
          <FocusPressable
            accessibilityLabel="Dictation unavailable"
            accessibilityRole="button"
            disabled
            style={({pressed}) => [
              styles.iconButton,
              pressed && styles.pressed,
            ]}>
            <Mic color="#666666" size={18} strokeWidth={2} />
          </FocusPressable>
          <View style={styles.actionSpacer} />
          <FocusPressable
            accessibilityLabel={
              activeGenerationId !== null
                ? 'Stop response'
                : omiBackend === undefined || omiBackend === null
                ? 'Send message unavailable'
                : 'Send message'
            }
            accessibilityRole="button"
            disabled={
              omiBackend === undefined ||
              omiBackend === null ||
              (activeGenerationId === null && (draft.trim() === '' || chatBusy))
            }
            onPress={activeGenerationId === null ? onSend : onStop}
            style={({pressed}) => [
              styles.sendButton,
              draft.trim() !== '' &&
                !chatBusy &&
                omiBackend !== undefined &&
                omiBackend !== null &&
                styles.sendButtonEnabled,
              activeGenerationId !== null && styles.stopButton,
              pressed && styles.pressed,
            ]}>
            {activeGenerationId === null ? (
              <ArrowUp color="#141414" size={18} strokeWidth={2.5} />
            ) : (
              <Square
                color="#141414"
                fill="#141414"
                size={13}
                strokeWidth={2}
              />
            )}
          </FocusPressable>
        </View>
      </View>
    </View>
  );
}
