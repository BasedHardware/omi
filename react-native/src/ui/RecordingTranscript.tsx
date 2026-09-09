import React from 'react';
import {ActivityIndicator, Text, View} from 'react-native';
import {visibleDisplayText} from '../desktopReadClient';
import {useRecordingTranscript} from '../recordingTranscript';
import {desktopTokens} from '../desktop/tokens';
import {FocusPressable} from './Pressable';
import {styles} from './styles';

export function RecordingTranscript({
  sessionId,
  revision,
  desktop = false,
}: {
  sessionId: string;
  revision?: string;
  desktop?: boolean;
}) {
  const {result, reload} = useRecordingTranscript(sessionId, revision);
  const ink = desktop ? {color: desktopTokens.color.ink} : undefined;
  const completedText =
    result.status === 'loaded' && result.value.state === 'completed'
      ? visibleDisplayText(result.value.text ?? '')
      : null;
  return (
    <View style={styles.conversationDetailFields}>
      <Text accessibilityRole="header" style={[styles.resultTitle, ink]}>
        Transcript
      </Text>
      {result.status === 'loading' || result.status === 'idle' ? (
        <View accessibilityLiveRegion="polite">
          <ActivityIndicator
            color={desktop ? desktopTokens.color.inkMuted : '#aaaaaa'}
          />
          <Text style={[styles.conversationDetailSummary, ink]}>
            Loading transcript…
          </Text>
        </View>
      ) : result.status === 'error' ? (
        <Text
          accessibilityRole="alert"
          style={[styles.conversationDetailSummary, ink]}>
          {result.retryable
            ? 'Transcript could not be loaded.'
            : 'Transcript is not available from this backend yet.'}
        </Text>
      ) : result.value.state === 'completed' ? (
        <>
          {result.value.discardedLeadingPackets > 0 && (
            <Text style={[styles.conversationDetailSummary, ink]}>
              Some audio at the beginning of this recording could not be
              decoded.
            </Text>
          )}
          <Text selectable style={[styles.conversationTranscriptText, ink]}>
            {completedText === '' ? 'The transcript is empty.' : completedText}
          </Text>
        </>
      ) : (
        <Text
          accessibilityLiveRegion="polite"
          style={[styles.conversationDetailSummary, ink]}>
          {result.value.state === 'failed'
            ? result.value.errorCode === 'attempt_limit'
              ? 'Transcription stopped after repeated failures. This recording cannot be retried.'
              : result.value.errorCode === 'invalid_audio'
              ? 'This recording could not be decoded for transcription. It cannot be retried.'
              : result.value.errorCode === 'invalid_transcript'
              ? 'This recording produced an invalid transcript. It cannot be retried.'
              : result.value.errorCode === 'transcription_unavailable'
              ? 'Transcription is unavailable for this recording. It cannot be retried.'
              : 'This recording could not be transcribed. It cannot be retried.'
            : result.value.state === 'queued'
            ? 'Transcription is queued.'
            : 'Transcription is in progress.'}
        </Text>
      )}
      {((result.status === 'error' && result.retryable) ||
        (result.status === 'loaded' && result.value.state !== 'completed')) && (
        <FocusPressable
          accessibilityRole="button"
          accessibilityLabel="Reload recording transcript"
          onPress={reload}
          style={styles.conversationTranscriptAction}>
          <Text style={[styles.conversationDetailField, ink]}>Check again</Text>
        </FocusPressable>
      )}
    </View>
  );
}
