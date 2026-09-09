import React from 'react';
import {TextInput, View} from 'react-native';
import ArrowUp from 'lucide-react-native/icons/arrow-up';
import Square from 'lucide-react-native/icons/square';
import {visibleDisplayText} from '../desktopReadClient';
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
  sendUnavailable,
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
  sendUnavailable: boolean;
}) {
  const backendMissing = omiBackend === undefined || omiBackend === null;
  const sendBlocked = backendMissing || sendUnavailable;
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
          editable={!sendBlocked}
          multiline
          onBlur={() => onFocusChange(false)}
          onChangeText={onDraftChange}
          onFocus={() => onFocusChange(true)}
          placeholder={
            sendBlocked
              ? 'Sending messages is not available on this backend yet.'
              : 'Ask anything...'
          }
          placeholderTextColor="#888888"
          ref={composerRef}
          style={[
            styles.composerInput,
            sendBlocked && styles.composerInputUnavailable,
          ]}
          value={draft}
        />
        <View style={styles.composerActions}>
          <View style={styles.actionSpacer} />
          <FocusPressable
            accessibilityLabel={
              activeGenerationId !== null
                ? 'Stop response'
                : sendBlocked
                ? 'Send message unavailable'
                : 'Send message'
            }
            accessibilityRole="button"
            disabled={
              sendBlocked ||
              (activeGenerationId === null &&
                (visibleDisplayText(draft) === '' || chatBusy))
            }
            onPress={activeGenerationId === null ? onSend : onStop}
            style={({pressed}) => [
              styles.sendButton,
              visibleDisplayText(draft) !== '' &&
                !chatBusy &&
                !sendBlocked &&
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
