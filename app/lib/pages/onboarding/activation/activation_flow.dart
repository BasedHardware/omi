import 'dart:async';

import 'package:flutter/material.dart';

import 'package:in_app_review/in_app_review.dart';
import 'package:permission_handler/permission_handler.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/onboarding/activation/activation_capture.dart';
import 'package:omi/pages/onboarding/activation/activation_visuals.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_plain_step.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/scanning_ripple.dart';

/// The stages of the first-run activation, in order. Some are skipped: [wear] without an Omi,
/// [microphone] with one (or when already allowed), [tasks] when Omi found none.
enum ActivationStage { wear, intro, notes, tasks, microphone, dictate, writing, summary, taskList, congrats }

/// Shows people what Omi does with their own words, then hands over to the paywall and Home.
///
/// Omi users first learn how to wear it; everyone sees "Let's see Omi at work.", two short animated
/// slides, then says a few sentences. Omi turns them into notes and tasks (a real conversation, first
/// on Home), then a congratulations screen. Skipping the dictation shows a welcome card on Home
/// instead.
class ActivationFlow extends StatefulWidget {
  const ActivationFlow({
    super.key,
    required this.hasDevice,
    required this.onFinished,
    this.capture,
    this.microphoneGranted,
    this.requestMicrophone,
    this.requestReview,
  });

  /// The reader connected an Omi in onboarding: they get the wear instructions and dictate through it.
  final bool hasDevice;

  /// Called once at the end (the paywall and Home follow).
  final VoidCallback onFinished;

  /// Defaults to the app's capture pipeline; replaceable in tests.
  final ActivationCapture Function(BuildContext context)? capture;
  final Future<bool> Function()? microphoneGranted;
  final Future<bool> Function()? requestMicrophone;
  final Future<void> Function()? requestReview;

  /// Set when the reader skipped the dictation, so Home shows the welcome card.
  static const welcomeCardKey = 'onboarding/showWelcomeCard';

  @override
  State<ActivationFlow> createState() => _ActivationFlowState();
}

class _ActivationFlowState extends State<ActivationFlow> {
  late ActivationStage _stage = widget.hasDevice ? ActivationStage.wear : ActivationStage.intro;
  ActivationResult? _result;
  bool _finished = false;

  void _track(String step) =>
      PlatformManager.instance.analytics.track('Onboarding Activation Step', properties: {'step': step});

  void _go(ActivationStage next) {
    if (!mounted) return;
    _track(next.name);
    setState(() => _stage = next);
  }

  Future<void> _afterSlides() async {
    if (widget.hasDevice) return _go(ActivationStage.dictate);
    final granted = await (widget.microphoneGranted ?? () => Permission.microphone.isGranted)();
    _go(granted ? ActivationStage.dictate : ActivationStage.microphone);
  }

  Future<void> _allowMicrophone() async {
    OmiHaptics.selection();
    final granted = await (widget.requestMicrophone ?? () async => (await Permission.microphone.request()).isGranted)();
    if (granted) {
      _go(ActivationStage.dictate);
    } else {
      _skipped();
    }
  }

  void _skipped() {
    SharedPreferencesUtil().saveBool(ActivationFlow.welcomeCardKey, true);
    _track('skipped');
    _go(ActivationStage.congrats);
  }

  void _dictated(Future<ActivationResult> result) {
    SharedPreferencesUtil().saveBool(ActivationFlow.welcomeCardKey, false);
    _go(ActivationStage.writing);
    // Keep "Writing your notes…" up long enough to read, even when Omi is quick.
    Future.wait([result, Future<void>.delayed(const Duration(milliseconds: 1600))]).then((values) {
      _result = values.first as ActivationResult;
      _go(ActivationStage.summary);
    });
  }

  ActivationCapture _newCapture(BuildContext context) {
    if (widget.capture != null) return widget.capture!(context);
    if (DemoActivationCapture.enabled) {
      final l10n = context.l10n;
      return DemoActivationCapture(
        script: l10n.onboardingActDictateExample,
        result: ActivationResult(
          transcript: '',
          emoji: '🥗',
          title: l10n.onboardingActDemoTitle,
          overview: l10n.onboardingActDemoSummary,
          tasks: [l10n.onboardingActDemoTask1, l10n.onboardingActDemoTask2],
        ),
      );
    }
    return PipelineActivationCapture(context);
  }

  void _finish() {
    if (_finished) return;
    _finished = true;
    widget.onFinished();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final Widget child = switch (_stage) {
      ActivationStage.wear => _Slide(
          key: const ValueKey('wear'),
          title: l10n.onboardingActWearTitle,
          body: l10n.onboardingActWearBody,
          visual: const _WearVisual(),
          onContinue: () => _go(ActivationStage.intro),
        ),
      ActivationStage.intro => _IntroLine(
          key: const ValueKey('intro'),
          text: l10n.onboardingActIntro,
          onDone: () => _go(ActivationStage.notes),
        ),
      ActivationStage.notes => _Slide(
          key: const ValueKey('notes'),
          title: l10n.onboardingActNotesTitle,
          body: l10n.onboardingActNotesBody,
          visual: NotesIllustration(title: l10n.onboardingActDemoTitle, summary: l10n.onboardingActDemoSummary),
          onContinue: () => _go(ActivationStage.tasks),
        ),
      ActivationStage.tasks => _Slide(
          key: const ValueKey('tasks'),
          title: l10n.onboardingActTasksTitle,
          body: l10n.onboardingActTasksBody,
          visual: TasksIllustration(tasks: [l10n.onboardingActDemoTask1, l10n.onboardingActDemoTask2]),
          onContinue: _afterSlides,
        ),
      ActivationStage.microphone => _Slide(
          key: const ValueKey('microphone'),
          title: l10n.onboardingActMicTitle,
          body: l10n.onboardingActMicBody,
          visual: const _MicVisual(),
          actionLabel: l10n.onboardingActMicAllow,
          onContinue: _allowMicrophone,
        ),
      ActivationStage.dictate => _DictationStep(
          key: const ValueKey('dictate'),
          capture: _newCapture(context),
          onDone: _dictated,
          onSkip: _skipped,
        ),
      ActivationStage.writing => _Writing(key: const ValueKey('writing'), label: l10n.onboardingActWriting),
      ActivationStage.summary => _SummaryReveal(
          key: const ValueKey('summary'),
          result: _result!,
          onContinue: () => _go(
            _result!.hasNotes && _result!.tasks.isNotEmpty ? ActivationStage.taskList : ActivationStage.congrats,
          ),
        ),
      ActivationStage.taskList => _TasksReveal(
          key: const ValueKey('taskList'),
          tasks: _result!.tasks,
          onContinue: () => _go(ActivationStage.congrats),
        ),
      ActivationStage.congrats => _Congrats(
          key: const ValueKey('congrats'),
          requestReview: widget.requestReview ?? InAppReview.instance.requestReview,
          onContinue: _finish,
        ),
    };
    final reduce = OmiMotion.of(context).emphasized == Duration.zero;
    return AnimatedSwitcher(
      duration: reduce ? Duration.zero : const Duration(milliseconds: 450),
      switchInCurve: Curves.easeOutCubic,
      switchOutCurve: Curves.easeInCubic,
      layoutBuilder: (current, previous) =>
          Stack(fit: StackFit.expand, children: [...previous, if (current != null) current]),
      transitionBuilder: (child, animation) => FadeTransition(
        opacity: animation,
        child: SlideTransition(
          position: Tween(begin: const Offset(0, 0.03), end: Offset.zero).animate(animation),
          child: child,
        ),
      ),
      child: child,
    );
  }
}

/// A title, a line, a visual in the middle and one button in the thumb spot.
class _Slide extends StatelessWidget {
  const _Slide({
    super.key,
    required this.title,
    required this.body,
    required this.visual,
    required this.onContinue,
    this.actionLabel,
  });

  final String title;
  final String body;
  final Widget visual;
  final VoidCallback onContinue;
  final String? actionLabel;

  @override
  Widget build(BuildContext context) {
    return OnboardingPlainStep(
      title: title,
      subtitle: body,
      centered: true,
      body: visual,
      action: OmiButton(
        key: Key('activation_continue_${(key as ValueKey?)?.value}'),
        label: actionLabel ?? context.l10n.continueButton,
        expand: true,
        onPressed: () {
          OmiHaptics.selection();
          onContinue();
        },
      ),
    );
  }
}

/// "Let's see Omi at work." Word by word, then moves on by itself. Nothing to tap.
class _IntroLine extends StatefulWidget {
  const _IntroLine({super.key, required this.text, required this.onDone});

  final String text;
  final VoidCallback onDone;

  @override
  State<_IntroLine> createState() => _IntroLineState();
}

class _IntroLineState extends State<_IntroLine> {
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer(const Duration(milliseconds: 3600), widget.onDone);
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final words = widget.text.split(' ');
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
        child: OneShot(
          duration: const Duration(milliseconds: 1800),
          builder: (context, t) => Wrap(
            alignment: WrapAlignment.center,
            children: [
              for (var i = 0; i < words.length; i++)
                rise(
                  segment(t, i / (words.length + 1), (i + 2) / (words.length + 1)),
                  Text('${words[i]} ', style: OmiType.largeTitle),
                  distance: 14,
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _WearVisual extends StatelessWidget {
  const _WearVisual();

  @override
  Widget build(BuildContext context) {
    return OneShot(
      duration: const Duration(milliseconds: 900),
      builder: (context, t) => rise(
        t,
        Center(
          child: Container(
            width: 160,
            height: 160,
            decoration: BoxDecoration(color: OmiColors.surface1, shape: BoxShape.circle),
            child: Center(child: Icon(Icons.graphic_eq_rounded, size: 64, color: OmiColors.textPrimary)),
          ),
        ),
        distance: 16,
      ),
    );
  }
}

class _MicVisual extends StatelessWidget {
  const _MicVisual();

  @override
  Widget build(BuildContext context) {
    return OneShot(
      duration: const Duration(milliseconds: 900),
      builder: (context, t) => rise(
        t,
        Center(
          child: Container(
            width: 120,
            height: 120,
            decoration: BoxDecoration(color: OmiColors.surface1, shape: BoxShape.circle),
            child: Center(child: Icon(Icons.mic_none_rounded, size: 52, color: OmiColors.textPrimary)),
          ),
        ),
        distance: 16,
      ),
    );
  }
}

/// "Tell Omi about your day": a note card that fills with the reader's words, and a bar with ×
/// (skip), the hint and ✓ (done, enabled once Omi has heard something).
class _DictationStep extends StatefulWidget {
  const _DictationStep({super.key, required this.capture, required this.onDone, required this.onSkip});

  final ActivationCapture capture;
  final void Function(Future<ActivationResult> result) onDone;
  final VoidCallback onSkip;

  @override
  State<_DictationStep> createState() => _DictationStepState();
}

class _DictationStepState extends State<_DictationStep> {
  bool _started = false;
  bool _failed = false;
  bool _leaving = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final ok = await widget.capture.start();
      if (!mounted) return;
      setState(() {
        _started = ok;
        _failed = !ok;
      });
    });
  }

  @override
  void dispose() {
    if (!_leaving) unawaited(widget.capture.cancel());
    super.dispose();
  }

  void _done() {
    if (_leaving) return;
    _leaving = true;
    OmiHaptics.selection();
    widget.onDone(widget.capture.finish());
  }

  Future<void> _skip() async {
    if (_leaving) return;
    _leaving = true;
    OmiHaptics.selection();
    await widget.capture.cancel();
    widget.onSkip();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final source = widget.capture.usesDevice ? 'Omi' : l10n.onboardingActPhoneMic;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, 0, OmiSpacing.xl, OmiSpacing.sm),
        child: ValueListenableBuilder<String>(
          valueListenable: widget.capture.liveText,
          builder: (context, text, _) {
            final heard = text.trim().isNotEmpty;
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Align(
                  alignment: Alignment.centerRight,
                  child: OmiButton.tertiary(
                    key: const Key('activation_dictation_skip'),
                    label: l10n.skip,
                    size: OmiButtonSize.compact,
                    onPressed: _skip,
                  ),
                ),
                const SizedBox(height: OmiSpacing.md),
                Semantics(
                  header: true,
                  child: Text(l10n.onboardingActDictateTitle, style: OmiType.title1, textAlign: TextAlign.center),
                ),
                const SizedBox(height: OmiSpacing.xs),
                Text(
                  l10n.onboardingActDictateBody,
                  style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                  textAlign: TextAlign.center,
                ),
                Expanded(
                  child: Center(
                    child: SingleChildScrollView(
                      child: AnimatedSize(
                        duration: const Duration(milliseconds: 200),
                        child: NoteCard(
                          key: const Key('activation_dictation_card'),
                          minHeight: 150,
                          child: Text(
                            heard ? text : l10n.onboardingActDictateExample,
                            style: OmiType.body.copyWith(
                              height: 1.45,
                              color: heard ? OmiColors.textPrimary : OmiColors.textTertiary,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
                _ListeningControl(
                  heard: heard,
                  listening: _started,
                  failed: _failed,
                  status: _failed
                      ? l10n.somethingWentWrong
                      : heard
                          ? l10n.onboardingActDictateHint
                          : '${l10n.listening} · $source',
                  onDone: _done,
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

/// The bottom of the dictation step, in the style of Connect Omi: soft rings around one round ✓
/// while Omi listens, and one quiet line under it. ✓ stays grey until Omi has heard something.
class _ListeningControl extends StatelessWidget {
  const _ListeningControl({
    required this.heard,
    required this.listening,
    required this.failed,
    required this.status,
    required this.onDone,
  });

  final bool heard;
  final bool listening;
  final bool failed;
  final String status;
  final VoidCallback onDone;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: 140,
          height: 140,
          child: Stack(
            alignment: Alignment.center,
            children: [
              if (listening && !failed)
                ScanningRippleWidget(isScanning: true, size: 140, color: OmiColors.textTertiary),
              Semantics(
                button: true,
                enabled: heard,
                label: l10n.done,
                excludeSemantics: true,
                child: GestureDetector(
                  key: const Key('activation_dictation_done'),
                  onTap: heard ? onDone : null,
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 250),
                    curve: Curves.easeOut,
                    width: 68,
                    height: 68,
                    decoration: BoxDecoration(
                      color: heard ? OmiColors.accent : OmiColors.surface3,
                      shape: BoxShape.circle,
                    ),
                    child: Icon(
                      Icons.check_rounded,
                      size: 32,
                      color: heard ? OmiColors.onAccent : OmiColors.textTertiary,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: OmiSpacing.xs),
        AnimatedSwitcher(
          duration: const Duration(milliseconds: 250),
          child: Text(
            status,
            key: ValueKey(status),
            textAlign: TextAlign.center,
            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
          ),
        ),
      ],
    );
  }
}

class _Writing extends StatelessWidget {
  const _Writing({super.key, required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const OmiSpinner(),
          const SizedBox(height: OmiSpacing.lg),
          Text(label, style: OmiType.title3, textAlign: TextAlign.center),
        ],
      ),
    );
  }
}

/// Omi's notes from the dictation: title, then the summary writing itself in.
class _SummaryReveal extends StatelessWidget {
  const _SummaryReveal({super.key, required this.result, required this.onContinue});

  final ActivationResult result;
  final VoidCallback onContinue;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final notes = result.hasNotes;
    final body = notes ? (result.overview.isEmpty ? result.transcript : result.overview) : result.transcript;
    return OnboardingPlainStep(
      title: notes ? l10n.onboardingActNotesLabel : l10n.onboardingActYourWords,
      centered: true,
      body: OneShot(
        duration: Duration(milliseconds: 600 + 40 * body.split(' ').length.clamp(10, 60)),
        builder: (context, t) => rise(
          segment(t, 0, 0.25),
          NoteCard(
            key: const Key('activation_summary_card'),
            emoji: notes ? result.emoji : null,
            title: notes && result.title.isNotEmpty ? result.title : null,
            child: WordReveal(
              text: body,
              t: segment(t, 0.2, 1, Curves.linear),
              style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.45),
            ),
          ),
          distance: 18,
        ),
      ),
      action: OmiButton(
        key: const Key('activation_continue_summary'),
        label: l10n.continueButton,
        expand: true,
        onPressed: () {
          OmiHaptics.selection();
          onContinue();
        },
      ),
    );
  }
}

/// The tasks Omi found, dropping in and ticking one by one.
class _TasksReveal extends StatelessWidget {
  const _TasksReveal({super.key, required this.tasks, required this.onContinue});

  final List<String> tasks;
  final VoidCallback onContinue;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final step = 1 / (tasks.length + 1);
    return OnboardingPlainStep(
      title: l10n.onboardingActTasksLabel,
      centered: true,
      body: OneShot(
        duration: Duration(milliseconds: 700 + 450 * tasks.length),
        builder: (context, t) => NoteCard(
          key: const Key('activation_tasks_card'),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              for (var i = 0; i < tasks.length; i++)
                rise(
                  segment(t, i * step * 0.8, i * step * 0.8 + step),
                  TaskRow(text: tasks[i], check: segment(t, (i + 1) * step * 0.8, (i + 1) * step * 0.8 + step * 0.6)),
                ),
            ],
          ),
        ),
      ),
      action: OmiButton(
        key: const Key('activation_continue_tasks'),
        label: l10n.continueButton,
        expand: true,
        onPressed: () {
          OmiHaptics.selection();
          onContinue();
        },
      ),
    );
  }
}

/// "You're all set": a check that draws itself, then the rating ask.
class _Congrats extends StatefulWidget {
  const _Congrats({super.key, required this.requestReview, required this.onContinue});

  final Future<void> Function() requestReview;
  final VoidCallback onContinue;

  @override
  State<_Congrats> createState() => _CongratsState();
}

class _CongratsState extends State<_Congrats> {
  bool _rated = false;

  @override
  void initState() {
    super.initState();
    OmiHaptics.success();
  }

  Future<void> _rate() async {
    if (_rated) return;
    setState(() => _rated = true);
    PlatformManager.instance.analytics.track('Onboarding Rating Asked', properties: {'answer': 'rate'});
    try {
      await widget.requestReview();
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final name = SharedPreferencesUtil().givenName.trim();
    return OnboardingPlainStep(
      title: name.isEmpty ? l10n.youreAllSet : l10n.onboardingActCongratsTitle(name),
      subtitle: l10n.onboardingActCongratsBody,
      centered: true,
      body: OneShot(
        duration: const Duration(milliseconds: 1600),
        builder: (context, t) => Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Transform.scale(
              scale: Curves.easeOutBack.transform(segment(t, 0, 0.4, Curves.linear)),
              child: Container(
                width: 88,
                height: 88,
                decoration: BoxDecoration(color: OmiColors.accent, shape: BoxShape.circle),
                child: Icon(Icons.check_rounded, size: 46, color: OmiColors.onAccent),
              ),
            ),
            const SizedBox(height: OmiSpacing.xxl),
            rise(
              segment(t, 0.5, 0.9),
              Container(
                padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md),
                decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
                child: Row(
                  children: [
                    Expanded(child: Text(l10n.onboardingActRateTitle, style: OmiType.callout)),
                    OmiButton.secondary(
                      key: const Key('activation_rate'),
                      label: l10n.onboardingActRateYes,
                      size: OmiButtonSize.compact,
                      onPressed: _rated ? null : _rate,
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
      action: OmiButton(
        key: const Key('activation_continue_congrats'),
        label: l10n.continueButton,
        expand: true,
        onPressed: widget.onContinue,
      ),
    );
  }
}
