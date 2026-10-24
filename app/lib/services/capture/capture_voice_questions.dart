part of 'capture_controller.dart';

/// Terminal outcomes for a submitted pendant question. Capture and the tutorial
/// share this path; chat-list projections never establish completion.
extension _CaptureVoiceQuestions on CaptureController {
  void _recordPendantVoiceQuestionDrop(PendantVoiceQuestionDroppedReason reason) {
    Logger.warning('Pendant voice question dropped: ${reason.wireName}');
    const TypedEvents().emit(PendantVoiceQuestionDropped(reason: reason));
  }

  Future<void> _processVoiceCommandBytes(
    String deviceId,
    List<List<int>> data, {
    bool allowWhenDisabled = false,
  }) async {
    final submissionGeneration = _voiceCommandSubmissionGeneration;
    final deviceRevision = _deviceIdentityRevision;
    final tutorial = allowWhenDisabled ? deviceOnboardingProvider : null;
    final attempt = tutorial?.questionAttempt;
    bool isCurrent() =>
        !_captureControllerDisposed &&
        submissionGeneration == _voiceCommandSubmissionGeneration &&
        (tutorial == null ||
            (identical(tutorial, deviceOnboardingProvider) && tutorial.acceptsQuestionResult(attempt!)));
    void finish(VoiceQuestionResult result) {
      if (isCurrent()) tutorial?.onVoiceQuestionFinished(result, attempt!);
    }

    if (_omiButtonActionsDisabled && !allowWhenDisabled) {
      _recordPendantVoiceQuestionDrop(PendantVoiceQuestionDroppedReason.actionsDisabled);
      return;
    }
    if (data.isEmpty) {
      _recordPendantVoiceQuestionDrop(PendantVoiceQuestionDroppedReason.emptyFrames);
      finish(const VoiceQuestionResult.failed(VoiceQuestionFailure.noSpeech));
      return;
    }
    if (_recordingDevice?.id != deviceId) {
      _recordPendantVoiceQuestionDrop(PendantVoiceQuestionDroppedReason.noDevice);
      finish(const VoiceQuestionResult.failed(VoiceQuestionFailure.unavailable));
      return;
    }
    late final BleAudioCodec codec;
    try {
      codec = await _getAudioCodec(_recordingDevice!.id).timeout(const Duration(seconds: 10));
    } catch (_) {
      _recordPendantVoiceQuestionDrop(PendantVoiceQuestionDroppedReason.codecLookupFailed);
      finish(const VoiceQuestionResult.failed(VoiceQuestionFailure.unavailable));
      return;
    }
    if (!isCurrent() || deviceRevision != _deviceIdentityRevision) {
      _recordPendantVoiceQuestionDrop(PendantVoiceQuestionDroppedReason.cancelled);
      finish(const VoiceQuestionResult.failed(VoiceQuestionFailure.unavailable));
      return;
    }
    if (_omiButtonActionsDisabled && !allowWhenDisabled) {
      _recordPendantVoiceQuestionDrop(PendantVoiceQuestionDroppedReason.actionsDisabled);
      return;
    }
    try {
      final result = await externalActions.sendVoiceMessageStreamToServer(
        data,
        onFirstChunkRecived: () {
          if (isCurrent()) _playSpeakerHaptic(deviceId, 2);
        },
        codec: codec,
        playResponseAudio: true,
        onNoSpeech: () async {
          if (!isCurrent()) return;
          // A best-effort vibration is not request-completion authority. A
          // stalled BLE lookup/write must not strand the tutorial or its retry.
          unawaited(_playVoiceQuestionFailureHaptic(deviceId).catchError((Object error) {
            Logger.warning('Pendant failure haptic failed: ${error.runtimeType}');
          }));
        },
      );
      finish(result);
    } catch (error) {
      Logger.warning('Pendant voice question failed: ${error.runtimeType}');
      finish(const VoiceQuestionResult.failed(VoiceQuestionFailure.unavailable));
    }
  }

  Future<void> _playVoiceQuestionFailureHaptic(String deviceId) async {
    if (!await _playSpeakerHaptic(deviceId, 1)) return;
    await Future<void>.delayed(const Duration(milliseconds: 80));
    await _playSpeakerHaptic(deviceId, 1);
  }
}
