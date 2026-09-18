import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'guided_voice_controller.dart';
import 'guided_voice_io.dart';

/// A bounded introduction: user-paced prompts, independent voice enrollment,
/// and explicit review before any personal statement becomes a memory.
class SpeechProfileWidget extends StatefulWidget {
  const SpeechProfileWidget({
    super.key,
    required this.goNext,
    required this.onSkip,
    this.controller,
    this.flowSource = 'first_run',
    this.flowVariant = 'guided_voice_v1',
  });
  final VoidCallback goNext;
  final VoidCallback onSkip;
  final GuidedVoiceController? controller;
  final String flowSource;
  final String flowVariant;

  @override
  State<SpeechProfileWidget> createState() => _SpeechProfileWidgetState();
}

class _SpeechProfileWidgetState extends State<SpeechProfileWidget> with WidgetsBindingObserver {
  late final GuidedVoiceController flow;
  bool _stoppingCapture = false;
  bool _attemptedSave = false;
  bool _finishing = false;
  Future<void>? _startTask;
  Future<void> Function()? _resumeCapture;
  bool _captureChecked = false;
  final _scrollController = ScrollController();
  int _shownPrompt = 0;

  @override
  void initState() {
    super.initState();
    flow = widget.controller ??
        GuidedVoiceController(DeviceGuidedVoiceIO(), flowSource: widget.flowSource, flowVariant: widget.flowVariant);
    flow.markStarted();
    WidgetsBinding.instance.addObserver(this);
    _shownPrompt = flow.promptIndex;
    flow.addListener(_showCurrentPrompt);
  }

  void _showCurrentPrompt() {
    if (_shownPrompt == flow.promptIndex) return;
    _shownPrompt = flow.promptIndex;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _scrollController.hasClients) _scrollController.jumpTo(0);
    });
  }

  @override
  void didChangeMetrics() {
    if (mounted) setState(() {});
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused || state == AppLifecycleState.hidden) unawaited(flow.pause());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    flow.removeListener(_showCurrentPrompt);
    _scrollController.dispose();
    if (widget.controller == null) flow.dispose();
    final resume = _resumeCapture;
    if (resume != null) {
      unawaited(() async {
        await _startTask;
        await resume();
      }());
    }
    super.dispose();
  }

  String copy(String part) => context.l10n.voiceIntroduction(part);

  Future<void> _start() => _startTask = _startRecording();

  Future<void> _startRecording() async {
    if (_stoppingCapture || flow.busy || flow.active) return;
    setState(() => _stoppingCapture = true);
    try {
      if (widget.controller == null && !_captureChecked) {
        _captureChecked = true;
        final capture = context.read<CaptureProvider>();
        if (capture.recordingState == RecordingState.deviceRecord) {
          final device = capture.recordingDevice;
          _resumeCapture = () async {
            await capture.streamDeviceRecording(device: device);
          };
          await capture.stopStreamDeviceRecording();
        } else if (capture.recordingState == RecordingState.record ||
            capture.recordingState == RecordingState.interrupted) {
          _resumeCapture = () async {
            await capture.streamRecording();
          };
          await capture.stopStreamRecording();
        }
      }
      if (mounted) await flow.start();
    } finally {
      if (mounted) setState(() => _stoppingCapture = false);
    }
  }

  Future<void> _saveAndFinish() async {
    if (flow.busy || _finishing) return;
    FocusScope.of(context).unfocus();
    setState(() => _attemptedSave = true);
    await flow.saveAll();
    if (!mounted) return;
    if (widget.controller == null && flow.goalSaved) {
      unawaited(context.read<GoalsProvider>().loadGoals());
    }
    if (flow.stage == IntroductionStage.done) {
      _finishing = true;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(copy('savedAll'))));
      widget.goNext();
    } else {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _scrollController.hasClients) {
          unawaited(_scrollController.animateTo(_scrollController.position.maxScrollExtent,
              duration: const Duration(milliseconds: 200), curve: Curves.easeOut));
        }
      });
    }
  }

  Future<void> _skip() async {
    flow.markSkipped();
    await flow.pause();
    if (mounted) widget.onSkip();
  }

  Widget _button(String text, VoidCallback? onPressed, String key, {bool secondary = false}) {
    return SizedBox(
      width: double.infinity,
      child: secondary
          ? OutlinedButton(
              key: Key(key),
              onPressed: onPressed,
              style: OutlinedButton.styleFrom(
                foregroundColor: Colors.white,
                minimumSize: const Size(0, 52),
                side: const BorderSide(color: Colors.white38),
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
              ),
              child: Text(text, textAlign: TextAlign.center))
          : FilledButton(
              key: Key(key),
              onPressed: onPressed,
              style: FilledButton.styleFrom(
                backgroundColor: Colors.white,
                foregroundColor: Colors.black,
                minimumSize: const Size(0, 56),
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
              ),
              child: Text(text, textAlign: TextAlign.center)),
    );
  }

  Widget _status(String text, {bool loading = false, bool success = false}) => Semantics(
        liveRegion: true,
        child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          if (loading)
            const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
          else
            Icon(success ? Icons.check_circle_outline : Icons.mic_none, size: 20, color: Colors.white),
          const SizedBox(width: 10),
          Flexible(child: Text(text, textAlign: TextAlign.center, style: const TextStyle(color: Colors.white70))),
        ]),
      );

  String get _prompt {
    if (flow.isGoalPrompt) return copy('goalPrompt');
    if (flow.alternative == 1) return copy('food');
    if (flow.alternative == 2) return copy('remember');
    return copy(['name', 'work', 'enjoy'][flow.promptIndex.clamp(0, 2)]);
  }

  Widget _recording() {
    final ready = flow.stage == IntroductionStage.ready;
    final paused = flow.stage == IntroductionStage.paused;
    final transcribing = flow.stage == IntroductionStage.transcribing;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Row(children: [
        Text('${flow.promptIndex + 1} / ${GuidedVoiceController.promptCount}',
            style: const TextStyle(color: Colors.white70, fontSize: 16)),
        const SizedBox(width: 16),
        Expanded(
            child: ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  key: const Key('introduction_progress'),
                  value: flow.progress,
                  minHeight: 6,
                  color: Colors.white,
                  backgroundColor: Colors.white24,
                  semanticsLabel: copy('title'),
                  semanticsValue: '${(flow.progress * 100).round()}%',
                ))),
      ]),
      const SizedBox(height: 28),
      Text(copy('hint'), style: const TextStyle(color: Colors.white70, height: 1.5, fontSize: 16)),
      const SizedBox(height: 20),
      Text(_prompt,
          key: const Key('introduction_prompt'),
          style: const TextStyle(
            color: Colors.white,
            fontSize: 30,
            height: 1.35,
            fontWeight: FontWeight.w600,
          )),
      const SizedBox(height: 12),
      if (ready && !flow.isGoalPrompt)
        Align(
            alignment: Alignment.centerLeft,
            child: TextButton(
              key: const Key('introduction_another'),
              onPressed: ready && !flow.isGoalPrompt ? flow.changePrompt : null,
              style: TextButton.styleFrom(foregroundColor: Colors.white70),
              child: Text(copy('another')),
            )),
      const SizedBox(height: 24),
      if (flow.active) ...[
        _status(flow.level > 0.04 ? copy('audio') : context.l10n.listening),
        const SizedBox(height: 12),
        Semantics(
            label: context.l10n.microphone,
            child: LinearProgressIndicator(
              key: const Key('introduction_audio_level'),
              value: flow.level,
              minHeight: 8,
              backgroundColor: Colors.white12,
              color: Colors.white,
            )),
        const SizedBox(height: 12),
        Text(copy('silence'), textAlign: TextAlign.center, style: const TextStyle(color: Colors.white70, height: 1.4)),
      ] else if (flow.busy || _stoppingCapture)
        _status(transcribing ? context.l10n.transcribing : context.l10n.loading, loading: true)
      else if (paused)
        _status(context.l10n.recordingPaused),
      const SizedBox(height: 20),
      ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 58),
          child: Text(
            flow.transcript,
            key: const Key('introduction_transcript'),
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: Colors.white70, fontSize: 17, height: 1.4),
          )),
      if (flow.error != null) ...[
        const SizedBox(height: 12),
        Text(flow.error == 'microphone' ? context.l10n.microphoneAccessDescription : copy('transcriptionError'),
            style: const TextStyle(color: Colors.white, height: 1.5)),
      ],
    ]);
  }

  Widget _review() => Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(copy('review'), style: const TextStyle(fontSize: 27, color: Colors.white, fontWeight: FontWeight.w600)),
        const SizedBox(height: 12),
        Text(copy('reviewHint'), style: const TextStyle(color: Colors.white70, height: 1.5, fontSize: 16)),
        const SizedBox(height: 20),
        for (var i = 0; i < flow.answers.length; i++) ...[
          DecoratedBox(
            decoration:
                BoxDecoration(color: Colors.white.withValues(alpha: 0.06), borderRadius: BorderRadius.circular(18)),
            child: Padding(
                padding: const EdgeInsets.fromLTRB(4, 8, 16, 8),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Checkbox(
                      value: flow.answers[i].keep,
                      activeColor: Colors.white,
                      checkColor: Colors.black,
                      onChanged:
                          flow.busy || flow.answers[i].locked ? null : (value) => flow.setKeep(i, value ?? false)),
                  Expanded(
                      child: TextFormField(
                    key: Key('introduction_memory_${flow.answers[i].id}_${flow.answers[i].editRevision}'),
                    initialValue: flow.answers[i].text,
                    minLines: 1,
                    maxLines: 5,
                    maxLength: flow.answers[i].isGoal ? 500 : null,
                    enabled: !flow.busy && !flow.answers[i].locked,
                    onChanged: (value) => flow.edit(i, value),
                    style: const TextStyle(color: Colors.white, height: 1.5),
                    decoration: InputDecoration(
                        border: InputBorder.none,
                        counterText: '',
                        labelText: flow.answers[i].isGoal ? context.l10n.myGoal : context.l10n.memories,
                        labelStyle: const TextStyle(color: Colors.white70)),
                  )),
                  if (flow.answers[i].saved)
                    const Padding(
                        padding: EdgeInsets.only(top: 14), child: Icon(Icons.check, color: Colors.white, size: 18)),
                ])),
          ),
          if (flow.answers[i].isGoal &&
              flow.answers[i].originalText != null &&
              flow.answers[i].originalText != flow.answers[i].text &&
              !flow.answers[i].locked)
            Align(
                alignment: Alignment.centerLeft,
                child: TextButton(
                  key: Key('introduction_original_${flow.answers[i].id}'),
                  onPressed: flow.busy ? null : () => flow.useOriginalGoal(i),
                  child: Text(copy('originalGoal'), style: const TextStyle(color: Colors.white70)),
                )),
          const SizedBox(height: 12),
        ],
        if (flow.answers.isEmpty) Text(copy('noMemories'), style: const TextStyle(color: Colors.white70, height: 1.5)),
        const SizedBox(height: 20),
        if (flow.stage == IntroductionStage.savingMemories) _status(copy('savingAnswers'), loading: true),
        if (flow.voiceSaved)
          _status(copy('savedVoice'), success: true)
        else if (flow.stage == IntroductionStage.savingVoice)
          _status(copy('savingVoice'), loading: true)
        else if (flow.voiceError == 'short')
          Text(copy('short'), style: const TextStyle(color: Colors.white, height: 1.5))
        else if (flow.voiceError == 'upload')
          Text(copy('uploadError'), style: const TextStyle(color: Colors.white, height: 1.5)),
        if (flow.voiceError == 'voiceUnavailable')
          Text(copy('voiceUnavailable'), style: const TextStyle(color: Colors.white, height: 1.5)),
        if (flow.error == 'goal' || flow.error == 'goalLong')
          Text(copy(flow.error == 'goal' ? 'goalError' : 'goalLong'),
              style: const TextStyle(color: Colors.white, height: 1.5)),
        if (flow.error == 'memories')
          Text(copy('memoryError'), style: const TextStyle(color: Colors.white, height: 1.5)),
      ]);

  List<Widget> _actions() {
    // Scaffold removes consumed insets from its body MediaQuery. Read the
    // view to retain keyboard visibility after the body has been resized.
    final editing = View.of(context).viewInsets.bottom > 0;
    if (flow.stage == IntroductionStage.done) {
      return [
        _button(context.l10n.continueButton, widget.goNext, 'introduction_continue'),
      ];
    }
    if (flow.promptIndex >= GuidedVoiceController.promptCount && flow.answers.isEmpty) {
      return [_button(context.l10n.continueButton, widget.onSkip, 'introduction_continue')];
    }
    if (flow.promptIndex >= GuidedVoiceController.promptCount) {
      return [
        _button(
            flow.busy
                ? context.l10n.saving
                : copy(_attemptedSave && flow.error != 'goalLong' ? 'retryRemaining' : 'saveFinish'),
            flow.busy ? null : () => unawaited(_saveAndFinish()),
            'introduction_save_all'),
        if (!_attemptedSave && !editing) ...[
          const SizedBox(height: 8),
          Text(copy('saveHint'),
              textAlign: TextAlign.center, style: const TextStyle(color: Colors.white70, fontSize: 13)),
        ],
        if (flow.voiceError == 'short' && !editing)
          TextButton(
            key: const Key('introduction_add_sample'),
            onPressed: flow.busy
                ? null
                : () {
                    flow.addSample();
                    unawaited(_start());
                  },
            child: Text(copy('addSample'), style: const TextStyle(color: Colors.white70)),
          ),
        if (!editing)
          TextButton(
              key: const Key('introduction_leave_review'),
              onPressed: flow.busy ? null : widget.goNext,
              child: Text(copy(_attemptedSave ? 'continueSaved' : 'without'),
                  textAlign: TextAlign.center, style: const TextStyle(color: Colors.white70))),
      ];
    }
    return [
      if (flow.busy)
        _button(flow.stage == IntroductionStage.transcribing ? context.l10n.transcribing : context.l10n.loading, null,
            'introduction_wait')
      else if (flow.active || (flow.stage == IntroductionStage.paused && flow.canFinish)) ...[
        _button(
            flow.promptIndex == GuidedVoiceController.promptCount - 1 ? copy('reviewAnswers') : context.l10n.nextButton,
            flow.canFinish && !flow.busy ? () => unawaited(flow.next()) : null,
            'introduction_next'),
        const SizedBox(height: 8),
        _button(
            flow.active ? context.l10n.pauseRecording : context.l10n.continueRecording,
            flow.busy
                ? null
                : () {
                    if (flow.active) {
                      unawaited(flow.pause());
                    } else {
                      unawaited(_start());
                    }
                  },
            'introduction_pause',
            secondary: true),
      ] else
        _button(
            copy('start'), flow.busy || _stoppingCapture ? null : () => unawaited(_start()), 'speech_profile_start'),
      const SizedBox(height: 8),
      Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Flexible(
            child: TextButton(
                key: const Key('introduction_skip_prompt'),
                onPressed: flow.busy ? null : () => unawaited(flow.skipPrompt()),
                child: Text(copy('skipPrompt'),
                    textAlign: TextAlign.center, style: const TextStyle(color: Colors.white70)))),
        Flexible(
            child: TextButton(
                key: const Key('speech_profile_skip_intro'),
                onPressed: () => unawaited(_skip()),
                child: Text(context.l10n.skipForNow, style: const TextStyle(color: Colors.white70)))),
      ]),
    ];
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
      animation: flow,
      builder: (context, _) {
        final done = flow.stage == IntroductionStage.done;
        return PopScope(
            canPop: !flow.saving,
            child: ColoredBox(
                color: Colors.black,
                child: SafeArea(
                    child: Column(children: [
                  Expanded(
                      child: SingleChildScrollView(
                    key: const Key('introduction_scroll'),
                    controller: _scrollController,
                    keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
                    padding: const EdgeInsets.fromLTRB(24, 20, 24, 20),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                      Text(copy('title'),
                          style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w600)),
                      if (flow.promptIndex == 0 && flow.stage == IntroductionStage.ready) ...[
                        const SizedBox(height: 12),
                        Text(copy('intro'), style: const TextStyle(color: Colors.white70, height: 1.5, fontSize: 16)),
                      ],
                      const SizedBox(height: 28),
                      if (done) ...[
                        const Icon(Icons.check_circle_outline, size: 64, color: Colors.white),
                        const SizedBox(height: 24),
                        _status(flow.savedMemoryCount > 0 ? copy('savedMemories') : copy('noMemories'), success: true),
                        if (flow.goalSaved) ...[const SizedBox(height: 16), _status(copy('savedGoal'), success: true)],
                        if (flow.voiceSaved) ...[
                          const SizedBox(height: 16),
                          _status(copy('savedVoice'), success: true)
                        ],
                      ] else if (flow.promptIndex >= GuidedVoiceController.promptCount)
                        _review()
                      else
                        _recording(),
                    ]),
                  )),
                  Padding(
                      padding: const EdgeInsets.fromLTRB(24, 8, 24, 12),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: _actions(),
                      )),
                ]))));
      });
}
