import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';

const _cardShadow = BoxShadow(
    color: Color(0x14000000), blurRadius: 24, offset: Offset(0, 8)); // omi-ux-allow: color-literal -- soft card shadow

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
        boxShadow: const [_cardShadow],
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

/// A burst of confetti from the centre: pieces fly out, turn and fade as [t] goes 0→1.
class ConfettiPainter extends CustomPainter {
  ConfettiPainter({required this.t});

  final double t;

  static const _colors = [
    Color(0xFFFFC53D), // omi-ux-allow: color-literal -- celebration confetti palette
    Color(0xFFFF6B6B), // omi-ux-allow: color-literal -- celebration confetti palette
    Color(0xFF4DABF7), // omi-ux-allow: color-literal -- celebration confetti palette
    Color(0xFF51CF66), // omi-ux-allow: color-literal -- celebration confetti palette
    Color(0xFF38D9A9), // omi-ux-allow: color-literal -- celebration confetti palette
    Color(0xFFFF922B), // omi-ux-allow: color-literal -- celebration confetti palette
  ];

  @override
  void paint(Canvas canvas, Size size) {
    if (t <= 0 || t >= 1) return;
    final center = size.center(Offset.zero);
    final random = math.Random(7);
    final travel = Curves.easeOutCubic.transform(t);
    final fade = t < 0.7 ? 1.0 : (1 - (t - 0.7) / 0.3);
    for (var i = 0; i < 36; i++) {
      final angle = random.nextDouble() * 2 * math.pi;
      final reach = size.width * (0.28 + random.nextDouble() * 0.24);
      final fall = 40 * t * t;
      final position = center + Offset(math.cos(angle) * reach * travel, math.sin(angle) * reach * travel + fall);
      final paint = Paint()..color = _colors[i % _colors.length].withValues(alpha: fade.clamp(0.0, 1.0));
      canvas.save();
      canvas.translate(position.dx, position.dy);
      canvas.rotate(angle + t * 6 * (random.nextBool() ? 1 : -1));
      final w = 5 + random.nextDouble() * 4;
      canvas.drawRRect(
        RRect.fromRectAndRadius(
            Rect.fromCenter(center: Offset.zero, width: w, height: w * 1.8), const Radius.circular(1.5)),
        paint,
      );
      canvas.restore();
    }
  }

  @override
  bool shouldRepaint(ConfettiPainter oldDelegate) => oldDelegate.t != t;
}
