import 'package:flutter/foundation.dart';

import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/ui/prompts/prompt_queue.dart';
import 'package:omi/utils/enums.dart';

/// Recording states in which a prompt would interrupt the person: phone-mic capture starting or
/// running, system-audio capture, and a mic taken by another app. Passive wearable capture
/// (`deviceRecord`) and a muted pendant (`pause`) are not busy — the same rule as the review
/// prompt (`widgets/app_review_prompt.dart`).
const Set<RecordingState> kPromptBlockingRecordingStates = {
  RecordingState.initialising,
  RecordingState.record,
  RecordingState.systemAudioRecord,
  RecordingState.interrupted,
};

const Set<PhoneCallState> kPromptBlockingCallStates = {
  PhoneCallState.connecting,
  PhoneCallState.ringing,
  PhoneCallState.active,
};

/// Whether startup and background prompts must wait (docs/ux-contract.md §14): recording, on a call,
/// or a firmware update running.
bool promptsBlocked({
  required RecordingState recordingState,
  required bool phoneMicBatchRecording,
  required bool micInterruptedByCall,
  required PhoneCallState callState,
  required bool firmwareUpdateInProgress,
}) {
  return kPromptBlockingRecordingStates.contains(recordingState) ||
      phoneMicBatchRecording ||
      micInterruptedByCall ||
      kPromptBlockingCallStates.contains(callState) ||
      firmwareUpdateInProgress;
}

/// Connects [PromptQueue] to the home shell's state: sets [PromptQueue.blocked] from the capture,
/// device and call state, and pumps the queue whenever that state changes so a held prompt appears
/// as soon as the person is free.
class HomePromptGate {
  HomePromptGate({PromptQueue? queue, ValueListenable<PhoneCallState>? callState})
      : _queue = queue ?? PromptQueue.instance,
        _callState = callState ?? PhoneCallProvider.callStateListenable;

  final PromptQueue _queue;
  final ValueListenable<PhoneCallState> _callState;
  CaptureProvider? _capture;
  DeviceProvider? _device;

  bool get isBlocked {
    final capture = _capture;
    final device = _device;
    return promptsBlocked(
      recordingState: capture?.recordingState ?? RecordingState.stop,
      phoneMicBatchRecording: capture?.isPhoneMicBatchRecording ?? false,
      micInterruptedByCall: capture?.isCallActive ?? false,
      callState: _callState.value,
      firmwareUpdateInProgress: device?.isFirmwareUpdateInProgress ?? false,
    );
  }

  void attach({required CaptureProvider capture, required DeviceProvider device}) {
    detach();
    _capture = capture..addListener(_onChanged);
    _device = device..addListener(_onChanged);
    _callState.addListener(_onChanged);
    _queue.blocked = () => isBlocked;
    _queue.pump();
  }

  void detach() {
    _capture?.removeListener(_onChanged);
    _device?.removeListener(_onChanged);
    if (_capture != null || _device != null) {
      _callState.removeListener(_onChanged);
      _queue.blocked = _never;
    }
    _capture = null;
    _device = null;
  }

  static bool _never() => false;

  /// Capture notifies often (every transcript segment), so this only pumps when something is waiting
  /// and nothing is on screen; [PromptQueue.pump] re-checks the hold and each prompt's condition.
  void _onChanged() {
    if (_queue.showingId != null || _queue.pendingIds.isEmpty || isBlocked) return;
    _queue.pump();
  }
}
