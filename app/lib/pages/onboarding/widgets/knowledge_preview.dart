import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';

/// The first-run "Here is what I know about you" picture (v2 `Knows`): the reader at the centre,
/// lit like the pendant's light, and the kinds of things Omi learns around them, joined by thin
/// lines. A sample — a new account has no memories yet — that draws itself in once: the centre, the
/// lines, then each topic (a still picture under Reduce Motion).
class OnboardingKnowledgePreview extends StatefulWidget {
  const OnboardingKnowledgePreview({super.key, required this.center, required this.topics})
      : assert(topics.length == 4, 'the picture has four topics');

  /// The reader's first name, or "You".
  final String center;

  /// Top left, top right, bottom left, bottom right.
  final List<String> topics;

  @override
  State<OnboardingKnowledgePreview> createState() => _OnboardingKnowledgePreviewState();
}

class _OnboardingKnowledgePreviewState extends State<OnboardingKnowledgePreview> with SingleTickerProviderStateMixin {
  late final AnimationController _draw = AnimationController(vsync: this, duration: const Duration(milliseconds: 1600));

  // Where the nodes sit, as fractions of the card (the v2 render's layout).
  static const _centre = Offset(0.5, 0.46);
  static const _nodes = [Offset(0.2, 0.22), Offset(0.78, 0.2), Offset(0.2, 0.74), Offset(0.78, 0.74)];

  // Lines: the centre to every topic, and two between topics (a web, not a star).
  static const _links = [(-1, 0), (-1, 1), (-1, 2), (-1, 3), (0, 1), (1, 3)];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      if (MediaQuery.maybeDisableAnimationsOf(context) ?? false) {
        _draw.value = 1;
      } else {
        _draw.forward();
      }
    });
  }

  @override
  void dispose() {
    _draw.dispose();
    super.dispose();
  }

  /// 0 → 1 over [start, end] of the drawing, eased.
  double _phase(double start, double end) =>
      Curves.easeOutCubic.transform(((_draw.value - start) / (end - start)).clamp(0.0, 1.0));

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: 1.3,
      child: OmiCard(
        radius: 32,
        padding: EdgeInsets.zero,
        clip: true,
        child: ExcludeSemantics(
          child: LayoutBuilder(
            builder: (context, box) {
              final size = box.biggest;
              Offset at(Offset f) => Offset(f.dx * size.width, f.dy * size.height);
              return AnimatedBuilder(
                animation: _draw,
                builder: (context, _) {
                  final centre = _phase(0, 0.3);
                  return Stack(
                    clipBehavior: Clip.none,
                    children: [
                      Positioned.fill(
                        child: CustomPaint(
                          painter: _LinksPainter(
                            centre: at(_centre),
                            nodes: [for (final n in _nodes) at(n)],
                            links: _links,
                            progress: _phase(0.15, 0.7),
                            color: OmiColors.textTertiary.withValues(alpha: 0.4),
                          ),
                        ),
                      ),
                      for (var i = 0; i < _nodes.length; i++)
                        _placed(
                          at(_nodes[i]),
                          _Topic(label: widget.topics[i], shown: _phase(0.35 + i * 0.12, 0.65 + i * 0.12)),
                        ),
                      _placed(at(_centre), _Centre(label: widget.center, shown: centre, glow: _phase(0.3, 1))),
                    ],
                  );
                },
              );
            },
          ),
        ),
      ),
    );
  }

  /// [child]'s dot sits on [point]; its label hangs under it.
  Widget _placed(Offset point, Widget child) {
    return Positioned(
      left: point.dx - 80,
      top: point.dy - _Centre.ring / 2,
      width: 160,
      child: child,
    );
  }
}

/// A topic: a small grey node and its name under it; it grows in from nothing.
class _Topic extends StatelessWidget {
  const _Topic({required this.label, required this.shown});

  final String label;
  final double shown;

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: shown,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            height: _Centre.ring,
            child: Center(
              child: Transform.scale(
                scale: 0.4 + 0.6 * shown,
                child: Container(
                  width: 14,
                  height: 14,
                  decoration: BoxDecoration(
                    color: OmiColors.textTertiary,
                    shape: BoxShape.circle,
                    border: Border.all(color: OmiColors.surface1, width: 2),
                  ),
                ),
              ),
            ),
          ),
          Transform.translate(
            offset: const Offset(0, -12),
            child: _Label(label,
                style: OmiType.footnote.copyWith(color: OmiColors.textPrimary, fontWeight: FontWeight.w500)),
          ),
        ],
      ),
    );
  }
}

/// The reader: a ring with the pendant's blue light at its heart and a soft halo, their name under.
class _Centre extends StatelessWidget {
  const _Centre({required this.label, required this.shown, required this.glow});

  static const double ring = 56;

  final String label;
  final double shown;
  final double glow;

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: shown,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            width: ring,
            height: ring,
            child: Stack(
              alignment: Alignment.center,
              clipBehavior: Clip.none,
              children: [
                // The halo opens as the web draws.
                Container(
                  width: ring + 22 * glow,
                  height: ring + 22 * glow,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: OmiColors.live.withValues(alpha: 0.12 * glow),
                  ),
                ),
                Container(
                  width: ring,
                  height: ring,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: OmiColors.surface2,
                    border: Border.all(color: OmiColors.textTertiary.withValues(alpha: 0.6), width: 1.5),
                  ),
                ),
                Container(
                  width: 12,
                  height: 12,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: OmiColors.live,
                    boxShadow: [BoxShadow(color: OmiColors.live.withValues(alpha: 0.6 * glow), blurRadius: 10)],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 6),
          _Label(label, style: OmiType.subhead.copyWith(color: OmiColors.textPrimary, fontWeight: FontWeight.w700)),
        ],
      ),
    );
  }
}

/// A node's name on a pad of the card's own colour, so the lines pass behind it, never through it.
class _Label extends StatelessWidget {
  const _Label(this.text, {required this.style});

  final String text;
  final TextStyle style;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: DecoratedBox(
        decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.smAll),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
          child: Text(text, maxLines: 1, overflow: TextOverflow.ellipsis, textAlign: TextAlign.center, style: style),
        ),
      ),
    );
  }
}

/// The web's lines, each drawn out from its first end as [progress] runs.
class _LinksPainter extends CustomPainter {
  _LinksPainter({
    required this.centre,
    required this.nodes,
    required this.links,
    required this.progress,
    required this.color,
  });

  final Offset centre;
  final List<Offset> nodes;
  final List<(int, int)> links;
  final double progress;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    if (progress <= 0) return;
    final paint = Paint()
      ..color = color
      ..strokeWidth = 1.2
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    for (var i = 0; i < links.length; i++) {
      final (from, to) = links[i];
      final a = from < 0 ? centre : nodes[from];
      final b = nodes[to];
      // Lines from the centre draw first, then the ones between topics.
      final local = ((progress - i * 0.08) / math.max(0.2, 1 - (links.length - 1) * 0.08)).clamp(0.0, 1.0);
      if (local <= 0) continue;
      canvas.drawLine(a, Offset.lerp(a, b, local)!, paint);
    }
  }

  @override
  bool shouldRepaint(_LinksPainter old) =>
      old.progress != progress || old.color != color || old.centre != centre || old.nodes != nodes;
}
