import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';

/// Runs [builder] with a 0→1 value once over [duration] (instant under Reduce Motion).
class OneShot extends StatefulWidget {
  const OneShot({super.key, required this.duration, required this.builder, this.delay = Duration.zero});

  final Duration duration;
  final Duration delay;
  final Widget Function(BuildContext context, double t) builder;

  @override
  State<OneShot> createState() => _OneShotState();
}

class _OneShotState extends State<OneShot> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: widget.duration);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_c.status != AnimationStatus.dismissed) return;
    if (OmiMotion.of(context).emphasized == Duration.zero) {
      _c.value = 1;
    } else {
      Future<void>.delayed(widget.delay, () {
        if (mounted) _c.forward();
      });
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) =>
      AnimatedBuilder(animation: _c, builder: (context, _) => widget.builder(context, _c.value));
}

/// The part of [t] that falls inside [start]..[end], eased, as 0→1.
double segment(double t, double start, double end, [Curve curve = Curves.easeOutCubic]) =>
    curve.transform(((t - start) / (end - start)).clamp(0.0, 1.0));

/// Fades and lifts [child] in as [t] goes 0→1.
Widget rise(double t, Widget child, {double distance = 10}) => Opacity(
      opacity: t,
      child: Transform.translate(offset: Offset(0, (1 - t) * distance), child: child),
    );

/// Animated listening bars. [active] keeps them moving; otherwise they rest low.
class ListeningBars extends StatefulWidget {
  const ListeningBars({super.key, this.active = true, this.count = 11, this.color, this.height = 22});

  final bool active;
  final int count;
  final Color? color;
  final double height;

  @override
  State<ListeningBars> createState() => _ListeningBarsState();
}

class _ListeningBarsState extends State<ListeningBars> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1400))
    ..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = widget.color ?? OmiColors.textPrimary;
    final reduce = OmiMotion.of(context).emphasized == Duration.zero;
    return SizedBox(
      height: widget.height,
      child: AnimatedBuilder(
        animation: _c,
        builder: (context, _) => Row(
          mainAxisSize: MainAxisSize.min,
          children: List.generate(widget.count, (i) {
            final phase = _c.value * 2 * math.pi + i * 0.7;
            final level = widget.active && !reduce ? (0.35 + 0.65 * (0.5 + 0.5 * math.sin(phase)).abs()) : 0.25;
            return Container(
              width: 4,
              height: math.max(4, widget.height * level),
              margin: const EdgeInsets.symmetric(horizontal: 2.5),
              decoration: BoxDecoration(color: color, borderRadius: OmiRadius.pillAll),
            );
          }),
        ),
      ),
    );
  }
}

/// A note card in the app's style: optional emoji + title, then body text.
class NoteCard extends StatelessWidget {
  const NoteCard({super.key, this.emoji, this.title, this.body, this.child, this.minHeight = 0});

  final String? emoji;
  final String? title;
  final String? body;
  final Widget? child;
  final double minHeight;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      constraints: BoxConstraints(minHeight: minHeight),
      padding: const EdgeInsets.all(OmiSpacing.lg),
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.lgAll,
        boxShadow: const [BoxShadow(color: Color(0x14000000), blurRadius: 24, offset: Offset(0, 8))],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (title != null)
            Text(
              emoji == null || emoji!.isEmpty ? title! : '${emoji!}  ${title!}',
              style: OmiType.headline,
            ),
          if (title != null && (body != null || child != null)) const SizedBox(height: OmiSpacing.xs),
          if (body != null) Text(body!, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.4)),
          if (child != null) child!,
        ],
      ),
    );
  }
}

/// One task row: a round check that fills at [check] (0→1) and the task text.
class TaskRow extends StatelessWidget {
  const TaskRow({super.key, required this.text, this.check = 0});

  final String text;
  final double check;

  @override
  Widget build(BuildContext context) {
    final fill = Color.lerp(Colors.transparent, OmiColors.accent, check)!;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xs),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 22,
            height: 22,
            margin: const EdgeInsets.only(top: 1),
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: fill,
              border: Border.all(color: Color.lerp(OmiColors.textTertiary, OmiColors.accent, check)!, width: 1.5),
            ),
            child: check > 0.5
                ? Icon(Icons.check_rounded, size: 15, color: OmiColors.onAccent.withValues(alpha: (check - 0.5) * 2))
                : null,
          ),
          const SizedBox(width: OmiSpacing.sm),
          Expanded(child: Text(text, style: OmiType.callout.copyWith(height: 1.35))),
        ],
      ),
    );
  }
}

/// Text that appears word by word as [t] goes 0→1.
class WordReveal extends StatelessWidget {
  const WordReveal({super.key, required this.text, required this.t, this.style, this.textAlign});

  final String text;
  final double t;
  final TextStyle? style;
  final TextAlign? textAlign;

  @override
  Widget build(BuildContext context) {
    final words = text.split(' ');
    final shown = (words.length * t).ceil().clamp(0, words.length);
    final base = style ?? DefaultTextStyle.of(context).style;
    return Text.rich(
      TextSpan(
        children: [
          for (var i = 0; i < words.length; i++)
            TextSpan(
              text: i == words.length - 1 ? words[i] : '${words[i]} ',
              style: base.copyWith(color: i < shown ? base.color : base.color?.withValues(alpha: 0)),
            ),
        ],
      ),
      textAlign: textAlign,
    );
  }
}

/// Slide 1: a voice (bars) becomes a note that writes itself.
class NotesIllustration extends StatelessWidget {
  const NotesIllustration({super.key, required this.title, required this.summary});

  final String title;
  final String summary;

  @override
  Widget build(BuildContext context) {
    return OneShot(
      duration: const Duration(milliseconds: 3800),
      delay: const Duration(milliseconds: 400),
      builder: (context, t) {
        final bars = 1 - segment(t, 0.3, 0.5);
        final card = segment(t, 0.35, 0.6);
        final text = segment(t, 0.55, 1.0, Curves.linear);
        return SizedBox(
          height: 220,
          child: Stack(
            alignment: Alignment.center,
            children: [
              Opacity(opacity: bars, child: const ListeningBars(height: 40, count: 13)),
              Opacity(
                opacity: card,
                child: Transform.scale(
                  scale: 0.92 + 0.08 * card,
                  child: NoteCard(
                    title: title,
                    emoji: '🥗',
                    child: WordReveal(
                      text: summary,
                      t: text,
                      style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.4),
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

/// Slide 2: the note gives way to tasks that tick themselves off.
class TasksIllustration extends StatelessWidget {
  const TasksIllustration({super.key, required this.tasks});

  final List<String> tasks;

  @override
  Widget build(BuildContext context) {
    return OneShot(
      duration: const Duration(milliseconds: 3400),
      delay: const Duration(milliseconds: 400),
      builder: (context, t) {
        return SizedBox(
          height: 220,
          child: Center(
            child: NoteCard(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  for (var i = 0; i < tasks.length; i++)
                    rise(
                      segment(t, 0.1 + i * 0.2, 0.4 + i * 0.2),
                      TaskRow(text: tasks[i], check: segment(t, 0.55 + i * 0.18, 0.75 + i * 0.18)),
                    ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}
