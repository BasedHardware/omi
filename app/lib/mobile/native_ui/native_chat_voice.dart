import 'package:flutter/material.dart';

import 'package:omi/pages/chat/widgets/voice_recorder_widget.dart';
import 'package:omi/providers/voice_recorder_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/l10n_extensions.dart';

import 'ios_native_surface.dart';

/// The existing recorder retains its microphone arbitration, WAV recovery and transcription.
/// Native controls only send the same Stop, Send, Retry and Discard commands.
List<NativeRow> nativeVoiceRows(
  BuildContext context,
  VoiceRecorderProvider voice,
) {
  final l10n = context.l10n;
  final recovering = voice.state == VoiceRecorderState.pendingRecovery;
  final failed = voice.state == VoiceRecorderState.transcribeFailed;
  final levels = voice.audioLevels;
  return [
    NativeRow(
      'chat_voice_status',
      voice.isRecording
          ? l10n.recording
          : recovering
              ? l10n.voiceRecordingFound
              : failed
                  ? l10n.voiceFailedToTranscribe
                  : l10n.transcribing,
      kind: 'label',
    ),
    if (voice.isRecording)
      NativeRow(
        'chat_voice_waveform',
        l10n.recording,
        kind: 'waveform',
        points: [
          for (var i = 0; i < levels.length; i++)
            {
              'x': i,
              'y': levels[i].isFinite ? levels[i].clamp(.05, 1.0) : .05,
              'label': '',
            },
        ],
      ),
    NativeRow(
      'chat_voice_discard',
      l10n.chatDiscardRecording,
      symbol: 'xmark',
      action: (_) => voice.discardRecording(),
    ),
    if (voice.isRecording) ...[
      NativeRow(
        'chat_voice_stop',
        l10n.stopRecording,
        symbol: 'stop.fill',
        action: (_) => voice.processRecording(),
      ),
      NativeRow(
        'chat_voice_send',
        l10n.chatSendMessage,
        symbol: 'arrow.up',
        action: (_) async {
          voice.requestAutoSendOnNextTranscript();
          await voice.processRecording();
        },
      ),
    ],
    if (recovering || failed)
      NativeRow(
        'chat_voice_retry',
        l10n.tryAgain,
        symbol: 'arrow.clockwise',
        action: (_) => voice.retry(),
      ),
  ];
}

/// Kept offstage by IosNativeSurface, exclusively when its native renderer is active.
/// The recorder's existing callback lifecycle is retained, including recovery on first open.
class NativeChatVoiceOwner extends StatefulWidget {
  const NativeChatVoiceOwner({
    super.key,
    required this.onTranscriptReady,
    required this.onClose,
  });
  final void Function(String transcript, bool autoSend) onTranscriptReady;
  final VoidCallback onClose;

  @override
  State<NativeChatVoiceOwner> createState() => _NativeChatVoiceOwnerState();
}

class _NativeChatVoiceOwnerState extends State<NativeChatVoiceOwner> {
  late final bool Function() _current;
  @override
  void initState() {
    super.initState();
    final owner = AuthService.instance.captureSessionSnapshot();
    _current = () => owner != null && AuthService.instance.isSessionSnapshotCurrent(owner);
  }

  @override
  Widget build(BuildContext context) => VoiceRecorderWidget(
        onTranscriptReady: (transcript, autoSend) {
          if (mounted && _current()) widget.onTranscriptReady(transcript, autoSend);
        },
        onClose: () {
          if (mounted && _current()) widget.onClose();
        },
      );
}
