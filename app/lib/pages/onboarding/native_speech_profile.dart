part of 'speech_profile_widget.dart';

extension _NativeSpeechProfile on _SpeechProfileWidgetState {
  Widget _nativeVoice(Widget fallback) {
    final actions = nativeButtonRows(_actions(), prefix: 'voice');
    if (actions == null) return fallback;
    final l10n = context.l10n;
    final done = flow.stage == IntroductionStage.done;
    final review = flow.promptIndex >= GuidedVoiceController.promptCount;
    return IosNativeSurface(
        title: copy(review && !done ? 'review' : 'title'),
        publicSurface: true,
        fallback: fallback,
        sections: [
          if (done)
            NativeSection('voice_receipt', [
              NativeRow('voice_memory_receipt', flow.savedMemoryCount > 0 ? copy('savedMemories') : copy('noMemories'),
                  kind: 'label', symbol: 'checkmark.circle'),
              if (flow.goalSaved)
                NativeRow('voice_goal_receipt', copy('savedGoal'), kind: 'label', symbol: 'checkmark.circle'),
              if (flow.voiceSaved)
                NativeRow('voice_enrollment_receipt', copy('savedVoice'), kind: 'label', symbol: 'checkmark.circle'),
            ])
          else if (review) ...[
            NativeSection('voice_review_hint', [NativeRow('voice_review_hint', copy('reviewHint'), kind: 'label')]),
            for (final (i, answer) in flow.answers.indexed)
              NativeSection('voice_answer_${answer.id}', [
                NativeRow('voice_keep_${answer.id}', answer.isGoal ? l10n.myGoal : l10n.memories,
                    kind: 'toggle',
                    value: answer.keep,
                    enabled: !flow.busy && !answer.locked,
                    action: (value) => flow.setKeep(i, value as bool)),
                NativeRow('voice_text_${answer.id}_${answer.editRevision}', answer.isGoal ? l10n.myGoal : l10n.memories,
                    kind: 'text',
                    value: answer.text,
                    maximumLength: answer.isGoal ? 500 : null,
                    enabled: !flow.busy && !answer.locked,
                    action: (value) => _editNativeAnswer(i, value as String)),
                if (answer.saved)
                  NativeRow('voice_saved_${answer.id}', copy(answer.isGoal ? 'savedGoal' : 'savedMemories'),
                      kind: 'label', symbol: 'checkmark.circle'),
                if (answer.isGoal &&
                    answer.originalText != null &&
                    answer.originalText != answer.text &&
                    !answer.locked)
                  NativeRow('voice_original_${answer.id}', copy('originalGoal'),
                      enabled: !flow.busy, action: (_) => flow.useOriginalGoal(i)),
              ]),
            NativeSection('voice_review_status', [
              if (flow.answers.isEmpty) NativeRow('voice_no_memories', copy('noMemories'), kind: 'label'),
              if (flow.stage == IntroductionStage.savingMemories)
                NativeRow('voice_saving_answers', copy('savingAnswers'),
                    kind: 'label', symbol: 'arrow.triangle.2.circlepath'),
              if (flow.voiceSaved)
                NativeRow('voice_saved_status', copy('savedVoice'), kind: 'label', symbol: 'checkmark.circle')
              else if (flow.stage == IntroductionStage.savingVoice)
                NativeRow('voice_saving', copy('savingVoice'), kind: 'label', symbol: 'arrow.triangle.2.circlepath'),
              if (flow.voiceError != null)
                NativeRow(
                    'voice_error',
                    copy(switch (flow.voiceError) {
                      'short' => 'short',
                      'upload' => 'uploadError',
                      _ => 'voiceUnavailable',
                    }),
                    kind: 'label'),
              if (flow.error == 'goal' || flow.error == 'goalLong' || flow.error == 'memories')
                NativeRow(
                    'voice_answer_error',
                    copy(switch (flow.error) {
                      'goal' => 'goalError',
                      'goalLong' => 'goalLong',
                      _ => 'memoryError',
                    }),
                    kind: 'label'),
            ]),
          ] else ...[
            NativeSection('voice_prompt', [
              NativeRow(
                  'voice_prompt_progress',
                  l10n.speakerTagPromptProgress((flow.promptIndex + 1).clamp(1, GuidedVoiceController.promptCount),
                      GuidedVoiceController.promptCount),
                  kind: 'label'),
              NativeRow('voice_prompt_text', _prompt, kind: 'label'),
              if (flow.stage == IntroductionStage.ready && !flow.isGoalPrompt)
                NativeRow('voice_another', copy('another'), action: (_) => flow.changePrompt()),
              if (flow.active) ...[
                NativeRow('voice_waveform', l10n.microphone, kind: 'waveform', points: [
                  for (final (i, level) in _waveform.indexed) {'x': i.toDouble(), 'y': level, 'label': ''}
                ]),
                if (flow.quiet) NativeRow('voice_silence', copy('silence'), kind: 'label'),
              ] else if (flow.busy || _stoppingCapture)
                NativeRow('voice_busy', flow.stage == IntroductionStage.transcribing ? l10n.transcribing : l10n.loading,
                    kind: 'label', symbol: 'arrow.triangle.2.circlepath')
              else if (flow.stage == IntroductionStage.paused)
                NativeRow('voice_paused', l10n.recordingPaused, kind: 'label', symbol: 'pause.circle'),
              if (flow.transcript.isNotEmpty) NativeRow('voice_transcript', flow.transcript, kind: 'label'),
              if (flow.error == 'microphone') ...[
                NativeRow('voice_microphone_reason', l10n.microphoneAccessDescription, kind: 'label'),
                if (_micStatus == OmiPermissionStatus.granted)
                  NativeRow('voice_microphone_allowed', l10n.permissionAllowed,
                      kind: 'label', symbol: 'checkmark.circle')
                else
                  NativeRow('voice_microphone_permission',
                      _micStatus == OmiPermissionStatus.askable ? l10n.allow : l10n.openSettings,
                      subtitle: _micStatus == OmiPermissionStatus.blocked ? l10n.permissionBlockedHint : '',
                      action: (_) async {
                    if (_micStatus == OmiPermissionStatus.askable) {
                      await _start();
                    } else {
                      await openAppSettings();
                    }
                  }),
              ] else if (flow.error != null)
                NativeRow('voice_transcription_error', copy('transcriptionError'), kind: 'label'),
            ]),
          ],
          NativeSection('voice_actions', actions),
        ]);
  }
}
