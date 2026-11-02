import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';

import 'package:omi/ui/omi_tokens.dart';

/// Announces [message] to the screen reader when it changes, instead of marking the whole
/// [child] subtree `liveRegion: true`. A live region re-announces on every semantics change, so
/// wrapping a per-second elapsed-time label in one re-announces the whole row every tick. Here
/// [message] carries only the capture-state transition (e.g. "Live" to "Paused"), not the ticking
/// elapsed text, so it only fires on a real state change; [child] keeps its own default semantics
/// so the current elapsed time still reads out when a screen reader user navigates to it.
class CaptureStateAnnouncement extends StatefulWidget {
  const CaptureStateAnnouncement({super.key, required this.message, required this.child});

  final String message;
  final Widget child;

  @override
  State<CaptureStateAnnouncement> createState() => _CaptureStateAnnouncementState();
}

class _CaptureStateAnnouncementState extends State<CaptureStateAnnouncement> {
  late String _lastAnnounced = widget.message;

  @override
  void didUpdateWidget(CaptureStateAnnouncement oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.message != _lastAnnounced) {
      _lastAnnounced = widget.message;
      SemanticsService.sendAnnouncement(View.of(context), widget.message, Directionality.of(context));
    }
  }

  @override
  Widget build(BuildContext context) => widget.child;
}

/// A thin arc that circles [child] while background work runs (offline sync, processing). Quiet
/// by design: no text, no colour, just motion around a glyph that already has a label. The arc
/// turns on a faint full track, so every frame reads as a ring. Under Reduce Motion it is still.
class OmiActivityRing extends StatefulWidget {
  const OmiActivityRing({
    super.key,
    required this.active,
    required this.child,
    this.diameter = 22,
    this.color,
    this.strokeWidth = 1.5,
  });

  /// The same ring on its own, sized to sit inline with a line of footnote text (a row that offline
  /// sync is still filling).
  const OmiActivityRing.inline({super.key, this.diameter = 12, this.color})
      : active = true,
        child = const SizedBox.shrink(),
        strokeWidth = 1.5;

  final bool active;
  final Widget child;
  final double strokeWidth;

  /// Outer size of the ring; the child is centred inside it.
  final double diameter;

  /// Arc colour. Defaults to [OmiColors.textSecondary].
  final Color? color;

  @override
  State<OmiActivityRing> createState() => _OmiActivityRingState();
}

class _OmiActivityRingState extends State<OmiActivityRing> with SingleTickerProviderStateMixin {
  late final AnimationController _spin = AnimationController(vsync: this, duration: const Duration(milliseconds: 1400));

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _sync();
  }

  @override
  void didUpdateWidget(OmiActivityRing oldWidget) {
    super.didUpdateWidget(oldWidget);
    _sync();
  }

  void _sync() {
    final reduceMotion = OmiMotion.of(context).standard == Duration.zero;
    if (widget.active && !reduceMotion && TickerMode.valuesOf(context).enabled) {
      if (!_spin.isAnimating) _spin.repeat();
    } else if (_spin.isAnimating) {
      _spin.stop();
    }
  }

  @override
  void dispose() {
    _spin.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox.square(
      dimension: widget.diameter,
      child: Stack(
        alignment: Alignment.center,
        children: [
          widget.child,
          if (widget.active)
            Positioned.fill(
              child: ExcludeSemantics(
                // Only the arc repaints. A transform without a boundary dirties the
                // surrounding header's display list on every animation frame.
                child: RepaintBoundary(
                  child: CustomPaint(
                    painter: _ArcPainter(_spin, widget.color ?? OmiColors.textSecondary, widget.strokeWidth),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _ArcPainter extends CustomPainter {
  _ArcPainter(this.turns, this.color, this.strokeWidth) : super(repaint: turns);

  final Animation<double> turns;

  final Color color;
  final double strokeWidth;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = (Offset.zero & size).deflate(strokeWidth / 2);
    final track = Paint()
      ..color = color.withValues(alpha: 0.25)
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth;
    final arc = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round;
    canvas.drawArc(rect, 0, math.pi * 2, false, track);
    canvas.drawArc(rect, -math.pi / 2 + turns.value * math.pi * 2, math.pi * 0.6, false, arc);
  }

  @override
  bool shouldRepaint(_ArcPainter oldDelegate) =>
      oldDelegate.turns != turns || oldDelegate.color != color || oldDelegate.strokeWidth != strokeWidth;
}

/// The live dot: green, gently pulsing while [live]; grey and still otherwise (paused, waiting).
/// Green is reserved for live and listening. Still under Reduce Motion.
class OmiLiveDot extends StatefulWidget {
  const OmiLiveDot({super.key, this.live = true, this.size = 10});

  final bool live;
  final double size;

  @override
  State<OmiLiveDot> createState() => _OmiLiveDotState();
}

class _OmiLiveDotState extends State<OmiLiveDot> with SingleTickerProviderStateMixin {
  late final AnimationController _pulse =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1600));

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reduceMotion = OmiMotion.of(context).standard == Duration.zero;
    if (widget.live && !reduceMotion) {
      if (!_pulse.isAnimating) _pulse.repeat(reverse: true);
    } else if (_pulse.isAnimating) {
      _pulse.stop();
    }
    final dot = Container(
      width: widget.size,
      height: widget.size,
      decoration:
          BoxDecoration(color: widget.live ? OmiColors.success : OmiColors.textTertiary, shape: BoxShape.circle),
    );
    if (!widget.live || reduceMotion) return dot;
    return FadeTransition(opacity: Tween<double>(begin: 1, end: 0.35).animate(_pulse), child: dot);
  }
}

/// A small live dot with one thin ring breathing out of it, every 2.4 s. The quiet live mark for
/// rows that sit among ordinary ones (Home's live episode): the primary text colour, no green
/// (David 2026-10-23). Grey and still when not [live], and still under Reduce Motion.
class OmiBreathingDot extends StatefulWidget {
  const OmiBreathingDot({super.key, this.live = true, this.size = 6});

  final bool live;
  final double size;

  @override
  State<OmiBreathingDot> createState() => _OmiBreathingDotState();
}

class _OmiBreathingDotState extends State<OmiBreathingDot> with SingleTickerProviderStateMixin {
  late final AnimationController _breath =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 2400));

  @override
  void dispose() {
    _breath.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reduceMotion = OmiMotion.of(context).standard == Duration.zero;
    final animate = widget.live && !reduceMotion && TickerMode.valuesOf(context).enabled;
    if (animate) {
      if (!_breath.isAnimating) _breath.repeat();
    } else if (_breath.isAnimating) {
      _breath.stop();
    }
    final color = widget.live ? OmiColors.textPrimary : OmiColors.textTertiary;
    final dot = Container(
        width: widget.size, height: widget.size, decoration: BoxDecoration(color: color, shape: BoxShape.circle));
    final extent = widget.size * 3;
    return SizedBox.square(
      dimension: extent,
      child: Stack(
        alignment: Alignment.center,
        children: [
          if (animate)
            ExcludeSemantics(
              child: RepaintBoundary(
                child: CustomPaint(
                  size: Size.square(extent),
                  painter: _BreathingRingPainter(_breath, color, widget.size),
                ),
              ),
            ),
          dot,
        ],
      ),
    );
  }
}

/// The ring changes only its paint, not widget size/layout or opacity layers.
class _BreathingRingPainter extends CustomPainter {
  _BreathingRingPainter(this.turns, this.color, this.dotSize) : super(repaint: turns);

  final Animation<double> turns;
  final Color color;
  final double dotSize;

  @override
  void paint(Canvas canvas, Size size) {
    final t = Curves.easeOut.transform(turns.value);
    final paint = Paint()
      ..color = color.withValues(alpha: color.a * (1 - t) * 0.6)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;
    // BoxDecoration's circular border was drawn inside the animated diameter.
    final radius = math.max(0.0, (dotSize * (1 + 1.6 * t) - 1) / 2);
    canvas.drawCircle(size.center(Offset.zero), radius, paint);
  }

  @override
  bool shouldRepaint(_BreathingRingPainter oldDelegate) =>
      oldDelegate.turns != turns || oldDelegate.color != color || oldDelegate.dotSize != dotSize;
}
