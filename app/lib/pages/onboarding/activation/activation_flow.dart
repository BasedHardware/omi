import 'dart:async';

import 'package:flutter/material.dart';

import 'package:in_app_review/in_app_review.dart';
import 'package:permission_handler/permission_handler.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/activation/activation_capture.dart';
import 'package:omi/pages/onboarding/activation/activation_visuals.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/scanning_ripple.dart';

/// Height of the row above every title: Skip sits in it on the dictation step.
const double _kTopRowHeight = 44;

/// Space between that row and every title: low enough to feel centred, high enough that the title
/// stays clear of the system prompts (microphone, App Store rating) that open mid-screen.
const double _kHeadingGap = 76;

/// The area under the card on dictation, "Summarizing…", the summary and the tasks. One height
/// for all four, so the card stays in the same place while the words turn into notes.
const double _kControlHeight = 172;

/// The stages of the first-run activation, in order. Some are skipped: [wear] without an Omi,
/// [microphone] with one (or when already allowed), [taskList] when Omi found no tasks.
enum ActivationStage { wear, intro, microphone, dictate, writing, summary, taskList, congrats, rating }

/// Shows people what Omi does with their own words, then hands over to the paywall and Home.
///
/// Omi users first learn how to wear it; everyone sees "Let's try Omi." and then says a few
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
  });

  /// The reader connected an Omi in onboarding: they get the wear instructions and dictate through it.
  final bool hasDevice;

  /// Called once at the very end; Home follows.
  final VoidCallback onFinished;

  /// Shows the paywall after the rating ask, last before Home; completes when it is closed.
  final Future<void> Function()? showPaywall;

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
  String _heard = '';
  ActivationResult? _result;
  bool _finished = false;

  void _track(String step) =>
      PlatformManager.instance.analytics.track('Onboarding Activation Step', properties: {'step': step});

  void _go(ActivationStage next) {
    if (!mounted) return;
    _track(next.name);
    setState(() => _stage = next);
  }

  Future<void> _afterIntro() async {
    if (widget.hasDevice) return _go(ActivationStage.dictate);
    final granted = await (widget.microphoneGranted ?? () => Permission.microphone.isGranted)();
    _go(granted ? ActivationStage.dictate : ActivationStage.microphone);
  }

  Future<void> _allowMicrophone() async {
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

  void _dictated(String heard, Future<ActivationResult> result) {
    SharedPreferencesUtil().saveBool(ActivationFlow.welcomeCardKey, false);
    _heard = heard;
    _go(ActivationStage.writing);
    // Keep "Summarizing…" up long enough to see the words being read, even when Omi is quick.
    Future.wait([result, Future<void>.delayed(const Duration(milliseconds: 1800))]).then((values) {
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

  Future<void> _afterRating() async {
    if (_finished) return;
    _finished = true;
    await widget.showPaywall?.call();
    widget.onFinished();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final Widget child = switch (_stage) {
      ActivationStage.wear => _Stage(
          key: const ValueKey('wear'),
          title: l10n.onboardingActWearTitle,
          subtitle: l10n.onboardingActWearBody,
          body: const _RoundVisual(icon: Icons.graphic_eq_rounded, size: 160),
          bottom: _ContinueButton(stage: 'wear', onPressed: () => _go(ActivationStage.intro)),
        ),
      ActivationStage.intro => _IntroLine(
          key: const ValueKey('intro'),
          text: l10n.onboardingActIntro,
          onDone: _afterIntro,
        ),
      ActivationStage.microphone => _Stage(
          key: const ValueKey('microphone'),
          title: l10n.onboardingActMicTitle,
          subtitle: l10n.onboardingActMicBody,
          body: const _RoundVisual(icon: Icons.mic_none_rounded, size: 120),
          bottom: _ContinueButton(
            stage: 'microphone',
            label: l10n.onboardingActMicAllow,
            onPressed: _allowMicrophone,
          ),
        ),
      ActivationStage.dictate => _DictationStep(
          key: const ValueKey('dictate'),
          capture: _newCapture(context),
          onDone: _dictated,
          onSkip: _skipped,
        ),
      ActivationStage.writing => _Stage(
          key: const ValueKey('writing'),
          title: l10n.onboardingActWriting,
          body: _ReadingCard(text: _heard),
          bottom: const _WorkingControl(),
          bottomHeight: _kControlHeight,
        ),
      ActivationStage.summary => _Stage(
          key: const ValueKey('summary'),
          title: _result!.hasNotes ? l10n.onboardingActNotesLabel : l10n.onboardingActYourWords,
          body: _SummaryCard(result: _result!, heard: _heard),
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
    this.subtitle,
    required this.body,
    this.bottom,
    this.topRight,
    this.bottomHeight,
    this.bodyAtTop = false,
  });

  final String title;
  final String? subtitle;
  final Widget body;
  final Widget? bottom;
  final Widget? topRight;
  final double? bottomHeight;
  final bool bodyAtTop;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, 0, OmiSpacing.xl, OmiSpacing.sm),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(
              height: _kTopRowHeight,
              child: Align(alignment: Alignment.centerRight, child: topRight),
            ),
            const SizedBox(height: _kHeadingGap),
            Semantics(header: true, child: Text(title, style: OmiType.title1, textAlign: TextAlign.center)),
            if (subtitle != null) ...[
              const SizedBox(height: OmiSpacing.xs),
              Text(
                subtitle!,
                style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                textAlign: TextAlign.center,
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

/// A large icon in a soft circle, rising in.
class _RoundVisual extends StatelessWidget {
  const _RoundVisual({required this.icon, required this.size});

  final IconData icon;
  final double size;

  @override
  Widget build(BuildContext context) {
    return OneShot(
      duration: const Duration(milliseconds: 900),
      builder: (context, t) => rise(
        t,
        Container(
          width: size,
          height: size,
          decoration: BoxDecoration(color: OmiColors.surface1, shape: BoxShape.circle),
          child: Icon(icon, size: size * 0.42, color: OmiColors.textPrimary),
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
  const _DictationStep({super.key, required this.capture, required this.onDone, required this.onSkip});

  final ActivationCapture capture;
  final void Function(String heard, Future<ActivationResult> result) onDone;
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
          subtitle: l10n.onboardingActDictateBody,
          topRight: _QuietSkip(label: l10n.skip, onTap: _skip),
          body: AnimatedSize(
            duration: const Duration(milliseconds: 200),
            child: _WordsCard(
              key: const Key('activation_dictation_card'),
              child: Text(
                heard ? text : l10n.onboardingActDictateExample,
                style: _wordsStyle.copyWith(color: heard ? OmiColors.textPrimary : OmiColors.textTertiary),
              ),
            ),
          ),
          bottom: _ListeningControl(
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
          bottomHeight: _kControlHeight,
        );
      },
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

/// Where the ✓ was: the same circle, now a sparkle that breathes while Omi reads the words.
class _WorkingControl extends StatefulWidget {
  const _WorkingControl();

  @override
  State<_WorkingControl> createState() => _WorkingControlState();
}

class _WorkingControlState extends State<_WorkingControl> with SingleTickerProviderStateMixin {
  late final AnimationController _pulse = AnimationController(vsync: this, duration: const Duration(milliseconds: 1100))
    ..repeat(reverse: true);

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reduce = OmiMotion.of(context).emphasized == Duration.zero;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: 140,
          height: 140,
          child: Stack(
            alignment: Alignment.center,
            children: [
              ScanningRippleWidget(isScanning: true, size: 140, color: OmiColors.textTertiary),
              AnimatedBuilder(
                animation: _pulse,
                builder: (context, child) => Transform.scale(
                  scale: reduce ? 1 : 1 + 0.06 * Curves.easeInOut.transform(_pulse.value),
                  child: child,
                ),
                child: Container(
                  width: 68,
                  height: 68,
                  decoration: BoxDecoration(color: OmiColors.accent, shape: BoxShape.circle),
                  child: Icon(Icons.auto_awesome_rounded, size: 30, color: OmiColors.onAccent),
                ),
              ),
            ],
          ),
        ),
        // Keeps the circle level with the ✓ it replaces (which has a status line under it).
        const SizedBox(height: OmiSpacing.xs + 20),
      ],
    );
  }
}

/// The reader's words in their card, with a light sweeping across them: Omi reading.
class _ReadingCard extends StatefulWidget {
  const _ReadingCard({required this.text});

  final String text;

  @override
  State<_ReadingCard> createState() => _ReadingCardState();
}

class _ReadingCardState extends State<_ReadingCard> with SingleTickerProviderStateMixin {
  late final AnimationController _sweep = AnimationController(vsync: this, duration: const Duration(milliseconds: 1300))
    ..repeat();

  @override
  void dispose() {
    _sweep.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reduce = OmiMotion.of(context).emphasized == Duration.zero;
    final text = Text(widget.text, style: _wordsStyle.copyWith(color: Colors.white));
    return _WordsCard(
      child: reduce
          ? Text(widget.text, style: _wordsStyle.copyWith(color: OmiColors.textSecondary))
          : AnimatedBuilder(
              animation: _sweep,
              builder: (context, child) {
                final x = -1.0 + 3.0 * _sweep.value;
                return ShaderMask(
                  blendMode: BlendMode.srcIn,
                  shaderCallback: (bounds) => LinearGradient(
                    begin: Alignment(x - 1, -0.3),
                    end: Alignment(x + 1, 0.3),
                    colors: [OmiColors.textTertiary, OmiColors.textPrimary, OmiColors.textTertiary],
                    stops: const [0.3, 0.5, 0.7],
                  ).createShader(bounds),
                  child: child,
                );
              },
              child: text,
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
          return _WordsCard(
            key: const Key('activation_summary_card'),
            child: WordReveal(text: _words, t: segment(t, 0, 1, Curves.linear), style: _wordsStyle),
          );
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
                      child: Text(_r.emoji, style: const TextStyle(fontSize: 22)),
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
              WordReveal(text: _summary, t: segment(t, 0.3, 0.9, Curves.linear), style: bodyStyle),
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

/// "You're all set": the title in its usual place, and under it a check that pops in with a burst
/// of confetti. One Continue.
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
      subtitle: l10n.onboardingActCongratsBody,
      body: OneShot(
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
  static const _gold = Color(0xFFFFC53D);
  Timer? _ask;
  bool _promptShowing = false;
  bool _done = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _ask = Timer(const Duration(milliseconds: 1500), _requestReview);
  }

  @override
  void dispose() {
    _ask?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  Future<void> _requestReview() async {
    PlatformManager.instance.analytics.track('Onboarding Rating Asked');
    try {
      await widget.requestReview();
    } catch (_) {}
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

  @override
  Widget build(BuildContext context) {
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
      bottom: OmiButton(
        key: const Key('activation_continue_rating'),
        label: context.l10n.continueButton,
        expand: true,
        onPressed: _leave,
      ),
    );
  }
}
