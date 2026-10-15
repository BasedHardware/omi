import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:in_app_review/in_app_review.dart';
import 'package:permission_handler/permission_handler.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/variants/yinka/activation/activation_capture.dart';
import 'package:omi/pages/onboarding/variants/yinka/activation/activation_motion.dart';
import 'package:omi/pages/onboarding/variants/yinka/activation/activation_visuals.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/scanning_ripple.dart';
import 'package:omi/pages/onboarding/variants/yinka/widgets/onboarding_card.dart';

/// Height of the row above every title: Skip sits in it on the dictation step.
const double _kTopRowHeight = 44;

/// Space between that row and every title: low enough to feel centred, high enough that the title
/// stays clear of the system prompts (microphone, App Store rating) that open mid-screen.
const double _kHeadingGap = 76;

/// The area under the card on dictation, "Summarizing…", the summary and the tasks. One height
/// for all four, so the card stays in the same place while the words turn into notes.
const double _kControlHeight = 172;

/// The stages of the first-run activation, in order. Some are skipped: [microphone] with an Omi (or
/// when already allowed), [taskList] when Omi found no tasks. How to wear and use an Omi is the
/// device tutorial Home shows after onboarding.
enum ActivationStage { intro, microphone, dictate, writing, summary, taskList, congrats, rating }

/// Shows people what Omi does with their own words, then hands over to the paywall and Home.
///
/// Everyone sees "Let's try Omi." and then says a few
/// sentences. Omi turns them into a summary and to-dos (a real conversation, first on Home), then
/// come a congratulations screen, the rating ask and the paywall. Skipping the dictation shows a
/// welcome card on Home instead.
class ActivationFlow extends StatefulWidget {
  const ActivationFlow({
    super.key,
    required this.hasDevice,
    required this.onFinished,
    this.showPaywall,
    this.capture,
    this.microphoneGranted,
    this.requestMicrophone,
    this.requestReview,
    this.notesDeadline = const Duration(seconds: 12),
  });

  /// The reader connected a wearable in onboarding: they dictate through it.
  final bool hasDevice;

  /// Called once at the very end; Home follows.
  /// Saves onboarding as done and leaves for Home; false when the save failed (the reader can retry).
  final Future<bool> Function() onFinished;

  /// Shows the paywall after the rating ask, last before Home; completes when it is closed.
  final Future<void> Function()? showPaywall;

  /// Defaults to the app's capture pipeline; replaceable in tests.
  final ActivationCapture Function(BuildContext context)? capture;
  final Future<bool> Function()? microphoneGranted;
  final Future<bool> Function()? requestMicrophone;
  final Future<void> Function()? requestReview;

  /// How long "Summarizing…" waits for Omi's notes. A few sentences usually take seconds; past this
  /// the reader moves on with their own words, and the notes arrive on Home.
  final Duration notesDeadline;

  /// Set when the reader skipped the dictation, so Home shows the welcome card.
  static const welcomeCardKey = 'onboarding/showWelcomeCard';

  @override
  State<ActivationFlow> createState() => _ActivationFlowState();
}

class _ActivationFlowState extends State<ActivationFlow> {
  ActivationStage _stage = ActivationStage.intro;
  ActivationCapture? _capture;

  /// The connected wearable was not streaming, so this dictation uses the phone microphone.
  bool _phoneInstead = false;
  String _heard = '';
  ActivationResult? _result;
  bool _finished = false;
  bool _paywallShown = false;

  void _track(String step) =>
      PlatformManager.instance.analytics.track('Onboarding Activation Step', properties: {'step': step});

  void _go(ActivationStage next) {
    if (!mounted) return;
    _track(next.name);
    // Each visit to the dictation listens afresh.
    if (next == ActivationStage.dictate) _capture = null;
    setState(() => _stage = next);
  }

  /// The wearable was not streaming and the phone microphone is not allowed yet.
  void _needsMicrophone() {
    _phoneInstead = true;
    _track('device_not_streaming');
    _go(ActivationStage.microphone);
  }

  Future<void> _afterIntro() async {
    if (widget.hasDevice) return _go(ActivationStage.dictate);
    final granted = await (widget.microphoneGranted ?? () => Permission.microphone.isGranted)();
    _go(granted ? ActivationStage.dictate : ActivationStage.microphone);
  }

  Future<void> _allowMicrophone() async {
    final granted = await (widget.requestMicrophone ?? () async => (await Permission.microphone.request()).isGranted)();
    if (granted) {
      OmiHaptics.light();
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

  void _dictated(String heard, Future<ActivationResult> result) {
    SharedPreferencesUtil().saveBool(ActivationFlow.welcomeCardKey, false);
    _heard = heard;
    _go(ActivationStage.writing);
    // Keep "Summarizing…" up long enough to see the words being read, even when Omi is quick.
    final notes = result.timeout(
      widget.notesDeadline,
      onTimeout: () => ActivationResult(transcript: heard, notesPending: true),
    );
    Future.wait([notes, Future<void>.delayed(const Duration(milliseconds: 1800))]).then((values) {
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
    return PipelineActivationCapture(context, expectDevice: widget.hasDevice && !_phoneInstead);
  }

  Future<void> _afterRating() async {
    if (_finished) return;
    _finished = true;
    if (!_paywallShown) {
      _paywallShown = true;
      await widget.showPaywall?.call();
    }
    // A failed save (the wrapper says so) must not strand the reader: Continue tries again.
    if (!await widget.onFinished()) _finished = false;
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final Widget child = switch (_stage) {
      ActivationStage.intro => _IntroLine(
          key: const ValueKey('intro'),
          text: l10n.onboardingActIntro,
          onDone: _afterIntro,
        ),
      ActivationStage.microphone => _Stage(
          key: const ValueKey('microphone'),
          title: l10n.onboardingActMicTitle,
          subtitle: _phoneInstead ? l10n.onboardingActMicFallbackBody : l10n.onboardingActMicBody,
          body: const _MicVisual(),
          bottom: _ContinueButton(
            stage: 'microphone',
            label: l10n.onboardingActMicAllow,
            onPressed: _allowMicrophone,
          ),
        ),
      ActivationStage.dictate => _DictationStep(
          key: const ValueKey('dictate'),
          capture: _capture ??= _newCapture(context),
          onDone: _dictated,
          onSkip: _skipped,
          onNeedsMicrophone: _needsMicrophone,
          throughOmi: widget.hasDevice && !_phoneInstead,
        ),
      ActivationStage.writing => _Stage(
          key: const ValueKey('writing'),
          title: l10n.onboardingActWriting,
          // The dictation's subtitle keeps its space (unseen), so the card doesn't move between the two.
          subtitle:
              widget.hasDevice && !_phoneInstead ? l10n.onboardingActDictateBodyOmi : l10n.onboardingActDictateBody,
          subtitleHidden: true,
          body: CompactingCard(text: _heard, style: _wordsStyle),
          bottom: const CondensingControl(),
          bottomHeight: _kControlHeight,
        ),
      ActivationStage.summary => _Stage(
          key: const ValueKey('summary'),
          eyebrow: l10n.onboardingActRemembers,
          title: _result!.hasNotes ? l10n.onboardingActNotesLabel : l10n.onboardingActYourWords,
          body: SummaryReveal(child: _SummaryCard(result: _result!, heard: _heard)),
          bottom: _ContinueButton(
            stage: 'summary',
            onPressed: () => _go(
              _result!.hasNotes && _result!.tasks.isNotEmpty ? ActivationStage.taskList : ActivationStage.congrats,
            ),
          ),
          bottomHeight: _kControlHeight,
        ),
      ActivationStage.taskList => _Stage(
          key: const ValueKey('taskList'),
          title: l10n.onboardingActTasksLabel,
          body: _TasksCard(tasks: _result!.tasks),
          bottom: _ContinueButton(stage: 'tasks', onPressed: () => _go(ActivationStage.congrats)),
          bottomHeight: _kControlHeight,
        ),
      ActivationStage.congrats =>
        _Hooray(key: const ValueKey('congrats'), onContinue: () => _go(ActivationStage.rating)),
      ActivationStage.rating => _RatingAsk(
          key: const ValueKey('rating'),
          requestReview: widget.requestReview ?? InAppReview.instance.requestReview,
          onDone: _afterRating,
        ),
    };
    final reduce = OmiMotion.of(context).emphasized == Duration.zero;
    return AnimatedSwitcher(
      duration: reduce ? Duration.zero : const Duration(milliseconds: 450),
      switchInCurve: Curves.easeOutCubic,
      switchOutCurve: Curves.easeInCubic,
      layoutBuilder: (current, previous) =>
          Stack(fit: StackFit.expand, children: [...previous, if (current != null) current]),
      transitionBuilder: (child, animation) => FadeTransition(opacity: animation, child: child),
      child: child,
    );
  }
}

/// Every titled activation screen. The title has one size and one height throughout, so moving from
/// step to step only changes what is under it. [bottomHeight] fixes the area under the body (so the
/// body sits in the same place on screens that share it); [bodyAtTop] puts the body right under
/// the title instead of in the middle.
class _Stage extends StatelessWidget {
  const _Stage({
    super.key,
    required this.title,
    this.eyebrow,
    this.subtitle,
    this.subtitleHidden = false,
    required this.body,
    this.bottom,
    this.topRight,
    this.bottomHeight,
    this.bodyAtTop = false,
  });

  final String title;

  /// A quiet line above the title.
  final String? eyebrow;
  final String? subtitle;

  /// Keeps the subtitle's space without showing it, so the body sits where it did on the step before.
  final bool subtitleHidden;
  final Widget body;
  final Widget? bottom;
  final Widget? topRight;
  final double? bottomHeight;
  final bool bodyAtTop;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, 0, OmiSpacing.xl, kOnboardingButtonBottomGap),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(
              height: _kTopRowHeight,
              child: Align(alignment: Alignment.centerRight, child: topRight),
            ),
            // The eyebrow takes its line out of the gap, so the title stays at the same height.
            SizedBox(height: eyebrow == null ? _kHeadingGap : _kHeadingGap - 26),
            if (eyebrow != null)
              SizedBox(
                height: 26,
                child: Text(
                  eyebrow!,
                  textAlign: TextAlign.center,
                  style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                ),
              ),
            Semantics(header: true, child: Text(title, style: OmiType.title1, textAlign: TextAlign.center)),
            if (subtitle != null) ...[
              const SizedBox(height: OmiSpacing.xs),
              Opacity(
                opacity: subtitleHidden ? 0 : 1,
                child: Text(
                  subtitle!,
                  style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                  textAlign: TextAlign.center,
                ),
              ),
            ],
            Expanded(
              child: bodyAtTop
                  ? Padding(
                      padding: const EdgeInsets.only(top: OmiSpacing.md),
                      child: Align(alignment: Alignment.topCenter, child: body),
                    )
                  : LayoutBuilder(
                      builder: (context, constraints) => SingleChildScrollView(
                        child: ConstrainedBox(
                          constraints: BoxConstraints(minHeight: constraints.maxHeight),
                          child: Center(child: body),
                        ),
                      ),
                    ),
            ),
            if (bottom != null)
              bottomHeight == null
                  ? Padding(padding: const EdgeInsets.only(top: OmiSpacing.md), child: bottom)
                  : SizedBox(height: bottomHeight, child: Align(alignment: Alignment.bottomCenter, child: bottom)),
          ],
        ),
      ),
    );
  }
}

class _ContinueButton extends StatelessWidget {
  const _ContinueButton({required this.stage, required this.onPressed, this.label});

  final String stage;
  final String? label;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return OmiButton(
      key: Key('activation_continue_$stage'),
      label: label ?? context.l10n.continueButton,
      expand: true,
      onPressed: () {
        OmiHaptics.selection();
        onPressed();
      },
    );
  }
}

/// "Let's try Omi." Word by word, then moves on by itself. Nothing to tap.
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
    _timer = Timer(const Duration(milliseconds: 3000), widget.onDone);
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
          duration: const Duration(milliseconds: 1400),
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

/// The microphone ask: the dark round control and soft ripple of the listening screen that follows,
/// so allowing the microphone feels like the first step of talking to Omi.
class _MicVisual extends StatelessWidget {
  const _MicVisual();

  static const double _size = 180;

  @override
  Widget build(BuildContext context) {
    return OneShot(
      duration: const Duration(milliseconds: 900),
      builder: (context, t) => rise(
        t,
        SizedBox(
          width: _size,
          height: _size,
          child: Stack(
            alignment: Alignment.center,
            children: [
              ScanningRippleWidget(isScanning: true, size: _size, color: OmiColors.textTertiary),
              Container(
                width: 112,
                height: 112,
                decoration: BoxDecoration(color: OmiColors.textPrimary.withValues(alpha: 0.06), shape: BoxShape.circle),
              ),
              Container(
                width: 80,
                height: 80,
                decoration: BoxDecoration(color: OmiColors.accent, shape: BoxShape.circle),
                child: Icon(Icons.mic_rounded, size: 36, color: OmiColors.onAccent),
              ),
            ],
          ),
        ),
        distance: 16,
      ),
    );
  }
}

/// The card that holds the reader's words, the same on the dictation and "Summarizing…" screens so
/// it reads as one card.
class _WordsCard extends StatelessWidget {
  const _WordsCard({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => NoteCard(minHeight: 150, child: child);
}

TextStyle get _wordsStyle => OmiType.body.copyWith(height: 1.45);

/// "Tell Omi about your day": a card that fills with the reader's words, Skip (grey, top right) and
/// a round ✓ (done, enabled once Omi has heard something).
class _DictationStep extends StatefulWidget {
  const _DictationStep({
    super.key,
    required this.capture,
    required this.onDone,
    required this.onSkip,
    required this.onNeedsMicrophone,
    this.throughOmi = false,
  });

  final ActivationCapture capture;
  final void Function(String heard, Future<ActivationResult> result) onDone;
  final VoidCallback onSkip;
  final VoidCallback onNeedsMicrophone;

  /// The reader dictates through their Omi, not the phone.
  final bool throughOmi;

  @override
  State<_DictationStep> createState() => _DictationStepState();
}

class _DictationStepState extends State<_DictationStep> {
  bool _started = false;
  bool _failed = false;
  bool _leaving = false;

  /// Nothing heard for a while after listening started: say so, instead of listening in silence.
  bool _quiet = false;
  Timer? _quietTimer;

  /// Still nothing heard well after the hint: offer a plain way on instead of a grey ✓ and a corner
  /// Skip (the microphone, the Omi or transcription may simply not be working right now).
  bool _stuck = false;
  Timer? _stuckTimer;

  @override
  void initState() {
    super.initState();
    widget.capture.liveText.addListener(_onWords);
    // From the moment the step opens, so a start that hangs (waiting for the Omi, the microphone)
    // still ends in Continue.
    _stuckTimer = Timer(const Duration(seconds: 25), () {
      if (mounted && widget.capture.liveText.value.trim().isEmpty) setState(() => _stuck = true);
    });
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final start = await widget.capture.start();
      if (!mounted) return;
      if (start == ActivationStart.needsMicrophone) {
        _leaving = true;
        widget.onNeedsMicrophone();
        return;
      }
      setState(() {
        _started = start == ActivationStart.listening;
        _failed = !_started;
      });
      if (_started) {
        _quietTimer = Timer(const Duration(seconds: 12), () {
          if (mounted && widget.capture.liveText.value.trim().isEmpty) setState(() => _quiet = true);
        });
      }
    });
  }

  bool _heardOnce = false;

  /// A light tap when the first words land: the moment Omi visibly understood.
  void _onWords() {
    if (_heardOnce || widget.capture.liveText.value.trim().isEmpty) return;
    _heardOnce = true;
    OmiHaptics.light();
  }

  @override
  void dispose() {
    widget.capture.liveText.removeListener(_onWords);
    _quietTimer?.cancel();
    _stuckTimer?.cancel();
    if (!_leaving) unawaited(widget.capture.cancel());
    super.dispose();
  }

  void _done() {
    if (_leaving) return;
    _leaving = true;
    OmiHaptics.medium();
    widget.onDone(widget.capture.liveText.value, widget.capture.finish());
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
    return ValueListenableBuilder<String>(
      valueListenable: widget.capture.liveText,
      builder: (context, text, _) {
        final heard = text.trim().isNotEmpty;
        return _Stage(
          title: l10n.onboardingActDictateTitle,
          subtitle: widget.throughOmi ? l10n.onboardingActDictateBodyOmi : l10n.onboardingActDictateBody,
          topRight: _QuietSkip(label: l10n.skip, onTap: _skip),
          body: ReadAlongCard(
            key: const Key('activation_dictation_card'),
            script: l10n.onboardingActDictateExample,
            live: widget.capture.liveText,
            level: widget.capture.level,
            listening: _started && !_failed,
            levelDriven: !widget.capture.usesDevice,
            style: _wordsStyle,
          ),
          // Words that arrive late still bring the ✓ back.
          bottom: !heard && (_failed || _stuck)
              ? _WayOn(
                  status: _failed
                      ? l10n.somethingWentWrong
                      : (widget.capture.usesDevice ? l10n.onboardingActNoAudioOmi : l10n.onboardingActNoAudioPhone),
                  onContinue: _skip,
                )
              : _ListeningControl(
                  level: widget.capture.level,
                  heard: heard,
                  listening: _started,
                  failed: _failed,
                  status: _failed
                      ? l10n.somethingWentWrong
                      : heard
                          ? l10n.onboardingActDictateHint
                          : !_started
                              ? l10n.listening
                              : _quiet
                                  ? (widget.capture.usesDevice
                                      ? l10n.onboardingActNoAudioOmi
                                      : l10n.onboardingActNoAudioPhone)
                                  : '${l10n.listening} · $source',
                  onDone: _done,
                ),
          bottomHeight: _kControlHeight,
        );
      },
    );
  }
}

/// The dictation's bottom when listening failed or nothing came through: what went wrong, in one
/// quiet line, and Continue (the same as Skip: the hooray, with a welcome card left for Home).
class _WayOn extends StatelessWidget {
  const _WayOn({required this.status, required this.onContinue});

  final String status;
  final VoidCallback onContinue;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          status,
          key: const Key('activation_dictation_status'),
          textAlign: TextAlign.center,
          style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
        ),
        const SizedBox(height: OmiSpacing.md),
        _ContinueButton(stage: 'dictation', onPressed: onContinue),
      ],
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
    required this.level,
  });

  /// How loud the person is right now: the ring around ✓ and the meter follow it, so it is
  /// obvious Omi hears them even before words come back.
  final ValueListenable<double> level;
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
              if (listening && !failed)
                ValueListenableBuilder<double>(
                  valueListenable: level,
                  builder: (context, v, _) => AnimatedContainer(
                    key: const Key('activation_voice_ring'),
                    duration: const Duration(milliseconds: 90),
                    curve: Curves.easeOut,
                    width: 76 + 60 * v,
                    height: 76 + 60 * v,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: OmiColors.textPrimary.withValues(alpha: 0.05 + 0.09 * v),
                    ),
                  ),
                ),
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
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (listening && !failed) ...[
              _LevelMeter(level: level),
              const SizedBox(width: OmiSpacing.xs),
            ],
            Flexible(
              child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 250),
                child: Text(
                  status,
                  key: ValueKey(status),
                  textAlign: TextAlign.center,
                  style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

/// Four small bars that move with the voice, next to "Listening".
class _LevelMeter extends StatelessWidget {
  const _LevelMeter({required this.level});

  final ValueListenable<double> level;

  static const _shape = [0.55, 1.0, 0.75, 0.4];

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: ValueListenableBuilder<double>(
        valueListenable: level,
        builder: (context, v, _) => Row(
          key: const Key('activation_level_meter'),
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            for (final s in _shape)
              AnimatedContainer(
                duration: const Duration(milliseconds: 90),
                margin: const EdgeInsets.symmetric(horizontal: 1),
                width: 3,
                height: 3 + 11 * (v * s).clamp(0.0, 1.0),
                decoration: BoxDecoration(
                  color: v > 0.05 ? OmiColors.textPrimary : OmiColors.textTertiary,
                  borderRadius: OmiRadius.pillAll,
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// What Omi made of the words, built in front of the reader the way it appears on Home: the emoji
/// pops in, the title and "Just now" rise, a line draws across, the summary writes itself, and the
/// reader's own words wait underneath behind "Transcript".
///
/// When Omi could not make notes, the card holds the reader's words alone.
class _SummaryCard extends StatefulWidget {
  const _SummaryCard({required this.result, required this.heard});

  final ActivationResult result;
  final String heard;

  @override
  State<_SummaryCard> createState() => _SummaryCardState();
}

class _SummaryCardState extends State<_SummaryCard> {
  final List<Timer> _beats = [];
  bool _showTranscript = false;

  ActivationResult get _r => widget.result;
  String get _words => _r.transcript.isNotEmpty ? _r.transcript : widget.heard;
  String get _summary => _r.overview.isNotEmpty ? _r.overview : _words;

  Duration get _duration => Duration(milliseconds: (900 + 55 * _summary.split(' ').length).clamp(1600, 4600));

  @override
  void initState() {
    super.initState();
    // A light tap as the emoji lands.
    if (_r.hasNotes) {
      _beats.add(Timer(Duration(milliseconds: (_duration.inMilliseconds * 0.12).round()), OmiHaptics.light));
    }
  }

  @override
  void dispose() {
    for (final beat in _beats) {
      beat.cancel();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final bodyStyle = OmiType.body.copyWith(color: OmiColors.textPrimary, height: 1.45);
    return OneShot(
      duration: _duration,
      builder: (context, t) {
        if (!_r.hasNotes) {
          final card = _WordsCard(
            key: const Key('activation_summary_card'),
            child: WordReveal(text: _words, t: segment(t, 0, 1, Curves.linear), style: _wordsStyle),
          );
          return card;
        }
        return NoteCard(
          key: const Key('activation_summary_card'),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  Transform.scale(
                    scale: Curves.elasticOut.transform(segment(t, 0.02, 0.3, Curves.linear)),
                    child: Container(
                      width: 44,
                      height: 44,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
                      child: Text(_r.emoji,
                          style: const TextStyle(
                              fontSize: 22)), // omi-ux-allow: font-size-literal -- emoji glyph sized to its 44 pt tile
                    ),
                  ),
                  const SizedBox(width: OmiSpacing.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        rise(segment(t, 0.08, 0.26), Text(_r.title, style: OmiType.headline), distance: 8),
                        const SizedBox(height: 2),
                        rise(
                          segment(t, 0.14, 0.32),
                          Text(l10n.onboardingActJustNow,
                              style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
                          distance: 6,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: OmiSpacing.md),
              Align(
                alignment: Alignment.centerLeft,
                child: FractionallySizedBox(
                  widthFactor: segment(t, 0.2, 0.4),
                  child: Container(height: 1, color: OmiColors.border),
                ),
              ),
              const SizedBox(height: OmiSpacing.md),
              SummaryText(text: _summary, t: segment(t, 0.3, 0.9, Curves.linear), style: bodyStyle),
              if (_words.isNotEmpty) ...[
                const SizedBox(height: OmiSpacing.md),
                rise(segment(t, 0.88, 1), _transcriptToggle(l10n), distance: 6),
              ],
            ],
          ),
        );
      },
    );
  }

  Widget _transcriptToggle(AppLocalizations l10n) {
    final quiet = OmiType.footnote.copyWith(color: OmiColors.textSecondary);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Semantics(
          button: true,
          expanded: _showTranscript,
          child: GestureDetector(
            key: const Key('activation_summary_transcript'),
            behavior: HitTestBehavior.opaque,
            onTap: () {
              OmiHaptics.selection();
              setState(() => _showTranscript = !_showTranscript);
            },
            child: SizedBox(
              height: 32,
              child: Row(
                children: [
                  Icon(Icons.graphic_eq_rounded, size: 16, color: OmiColors.textTertiary),
                  const SizedBox(width: OmiSpacing.xs),
                  Expanded(child: Text(l10n.transcript, style: quiet)),
                  AnimatedRotation(
                    turns: _showTranscript ? 0.5 : 0,
                    duration: const Duration(milliseconds: 200),
                    child: Icon(Icons.expand_more_rounded, size: 18, color: OmiColors.textTertiary),
                  ),
                ],
              ),
            ),
          ),
        ),
        AnimatedSize(
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOutCubic,
          alignment: Alignment.topCenter,
          child: _showTranscript
              ? Padding(
                  padding: const EdgeInsets.only(top: OmiSpacing.xs),
                  child: Text(_words, style: quiet.copyWith(color: OmiColors.textTertiary, height: 1.4)),
                )
              : const SizedBox(width: double.infinity),
        ),
      ],
    );
  }
}

/// The to-dos Omi caught, sliding in one by one with a tap each, then "Saved to your tasks".
class _TasksCard extends StatefulWidget {
  const _TasksCard({required this.tasks});

  final List<String> tasks;

  @override
  State<_TasksCard> createState() => _TasksCardState();
}

class _TasksCardState extends State<_TasksCard> {
  final List<Timer> _beats = [];
  static const _first = 300;
  static const _gap = 520;

  int get _n => widget.tasks.length;
  Duration get _duration => Duration(milliseconds: _first + _gap * _n + 900);

  /// When task [i] arrives, as a share of [_duration].
  double _at(int i) => (_first + _gap * i) / _duration.inMilliseconds;

  @override
  void initState() {
    super.initState();
    for (var i = 0; i < _n; i++) {
      _beats.add(Timer(Duration(milliseconds: _first + _gap * i + 120), OmiHaptics.light));
    }
    _beats.add(Timer(Duration(milliseconds: _first + _gap * _n + 200), OmiHaptics.success));
  }

  @override
  void dispose() {
    for (final beat in _beats) {
      beat.cancel();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final span = _gap / _duration.inMilliseconds;
    return OneShot(
      duration: _duration,
      builder: (context, t) {
        final saved = segment(t, _at(_n), _at(_n) + span);
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            NoteCard(
              key: const Key('activation_tasks_card'),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  for (var i = 0; i < _n; i++) ...[
                    if (i > 0) Container(height: 1, color: OmiColors.border),
                    _arriving(segment(t, _at(i), _at(i) + span * 1.4, Curves.linear), widget.tasks[i]),
                  ],
                ],
              ),
            ),
            const SizedBox(height: OmiSpacing.md),
            Opacity(
              opacity: saved,
              child: Transform.scale(
                scale: 0.9 + 0.1 * Curves.easeOutBack.transform(saved),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.xs),
                  decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.pillAll),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.check_circle_rounded, size: 16, color: OmiColors.success),
                      const SizedBox(width: OmiSpacing.xs),
                      Text(l10n.onboardingActSavedToTasks,
                          style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                    ],
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  /// One task sliding in from the right with a brief highlight behind it as it lands.
  Widget _arriving(double p, String text) {
    final move = Curves.easeOutBack.transform(p.clamp(0.0, 1.0));
    final glow = p <= 0 ? 0.0 : (1 - p).clamp(0.0, 1.0);
    return Opacity(
      opacity: segment(p, 0, 0.4),
      child: Transform.translate(
        offset: Offset((1 - move) * 36, 0),
        child: Container(
          decoration: BoxDecoration(
            color: OmiColors.accent.withValues(alpha: 0.06 * glow),
            borderRadius: OmiRadius.smAll,
          ),
          padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xxs),
          child: TaskRow(text: text),
        ),
      ),
    );
  }
}

/// Skip in the top right, in grey: there if needed, without competing with the dictation.
class _QuietSkip extends StatelessWidget {
  const _QuietSkip({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: label,
      excludeSemantics: true,
      child: GestureDetector(
        key: const Key('activation_dictation_skip'),
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
          child: Center(
            widthFactor: 1,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xs),
              child: Text(label, style: OmiType.callout.copyWith(color: OmiColors.textTertiary)),
            ),
          ),
        ),
      ),
    );
  }
}

/// "You're all set": the title in its usual place, and close under it a check that pops in with a
/// burst of confetti. One Continue.
class _Hooray extends StatefulWidget {
  const _Hooray({super.key, required this.onContinue});

  final VoidCallback onContinue;

  @override
  State<_Hooray> createState() => _HoorayState();
}

class _HoorayState extends State<_Hooray> {
  Timer? _haptic;

  @override
  void initState() {
    super.initState();
    // In step with the check popping in.
    _haptic = Timer(const Duration(milliseconds: 380), OmiHaptics.success);
  }

  @override
  void dispose() {
    _haptic?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final name = SharedPreferencesUtil().givenName.trim();
    return _Stage(
      title: name.isEmpty ? l10n.youreAllSet : l10n.onboardingActCongratsTitle(name),
      // Lifted above the middle so the check sits close under the title.
      body: Padding(
        padding: const EdgeInsets.only(bottom: 120),
        child: OneShot(
          duration: const Duration(milliseconds: 2000),
          builder: (context, t) => SizedBox(
            width: 280,
            height: 280,
            child: Stack(
              alignment: Alignment.center,
              children: [
                Positioned.fill(child: CustomPaint(painter: ConfettiPainter(t: segment(t, 0.2, 1, Curves.linear)))),
                Transform.scale(
                  scale: Curves.elasticOut.transform(segment(t, 0.12, 0.55, Curves.linear)),
                  child: Container(
                    width: 104,
                    height: 104,
                    decoration: BoxDecoration(color: OmiColors.accent, shape: BoxShape.circle),
                    child: Icon(Icons.check_rounded, size: 56, color: OmiColors.onAccent),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
      bottom: _ContinueButton(stage: 'congrats', onPressed: widget.onContinue),
    );
  }
}

/// After the celebration: "Enjoying Omi so far?" with five gold stars popping in one by one under
/// it, both above where the App Store rating pop-up opens by itself. The paywall follows once the
/// pop-up is closed (or Continue, if it never showed).
class _RatingAsk extends StatefulWidget {
  const _RatingAsk({super.key, required this.requestReview, required this.onDone});

  final Future<void> Function() requestReview;
  final VoidCallback onDone;

  @override
  State<_RatingAsk> createState() => _RatingAskState();
}

class _RatingAskState extends State<_RatingAsk> with WidgetsBindingObserver {
  static const _gold = Color(0xFFFFC53D); // omi-ux-allow: color-literal -- rating stars in App Store gold
  Timer? _ask;
  Timer? _starsLanded;
  Timer? _offerContinue;
  bool _promptShowing = false;
  // Continue stays hidden until the App Store pop-up has had time to appear, so a quick tap can't
  // skip past it.
  bool _canContinue = false;
  bool _asked = false;
  bool _done = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // A light tap as the stars land, then the App Store prompt.
    _starsLanded = Timer(const Duration(milliseconds: 650), OmiHaptics.light);
    _ask = Timer(const Duration(milliseconds: 1500), _requestReview);
  }

  @override
  void dispose() {
    _ask?.cancel();
    _starsLanded?.cancel();
    _offerContinue?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  Future<void> _requestReview() async {
    PlatformManager.instance.analytics.track('Onboarding Rating Asked');
    try {
      await widget.requestReview();
    } catch (_) {}
    _asked = true;
    // iOS gives no callback when its pop-up closes (and on many builds the app never goes
    // inactive under it), so don't wait for it: once it is up, move on underneath it. Closing it
    // then lands on the paywall instead of back on this screen.
    _offerContinue = Timer(const Duration(milliseconds: 900), () {
      if (!mounted) return;
      // Continue stays as the way on if leaving fails (a failed save is retried from here).
      setState(() => _canContinue = true);
      _leave();
    });
  }

  /// iOS gives no callback for its rating pop-up, but the app goes inactive while it is up and
  /// becomes active again when it closes: that return is the cue to move on.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive) _promptShowing = true;
    if (state == AppLifecycleState.resumed && _promptShowing) _leave();
  }

  void _leave() {
    if (_done || !mounted) return;
    _done = true;
    widget.onDone();
  }

  /// Continue always reaches [widget.onDone], so a failed save can be retried.
  void _continue() {
    if (!mounted) return;
    _done = true;
    widget.onDone();
  }

  @override
  Widget build(BuildContext context) {
    // Not every iOS build makes the app inactive under the pop-up (the simulator never does). The
    // pop-up takes every touch while it is up, so the first tap here after asking means it closed.
    return Listener(
      behavior: HitTestBehavior.translucent,
      // After the tap has been handled: a tap on Continue has then already moved on (or retried a
      // failed save), and this cue must not count the same tap twice.
      onPointerUp: (_) {
        if (_asked && _canContinue) Future<void>(_leave);
      },
      child: _buildStage(context),
    );
  }

  Widget _buildStage(BuildContext context) {
    return _Stage(
      title: context.l10n.onboardingActRateTitle,
      bodyAtTop: true,
      body: OneShot(
        duration: const Duration(milliseconds: 1200),
        builder: (context, t) => Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            for (var i = 0; i < 5; i++)
              Transform.scale(
                scale: Curves.elasticOut.transform(segment(t, i * 0.1, 0.45 + i * 0.1, Curves.linear)),
                child: const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 3),
                  child: Icon(Icons.star_rounded, size: 46, color: _gold),
                ),
              ),
          ],
        ),
      ),
      bottom: IgnorePointer(
        ignoring: !_canContinue,
        child: AnimatedOpacity(
          opacity: _canContinue ? 1 : 0,
          duration: const Duration(milliseconds: 300),
          child: OmiButton(
            key: const Key('activation_continue_rating'),
            label: context.l10n.continueButton,
            expand: true,
            onPressed: _continue,
          ),
        ),
      ),
    );
  }
}
