import 'package:flutter/material.dart';

import 'package:omi/utils/app_typography.dart';

/// The Home entry surface: the headline, then the "Ask Omi" bar beneath it.
///
/// On first load the two stagger in — the headline settles, and the bar follows
/// once it is most of the way there. The stagger is the point: it reads as the
/// product introducing itself and then offering the way in, rather than a panel
/// appearing all at once.
///
/// [animate] is owned by the host so the entrance plays once per launch. The
/// widget is mounted and unmounted by the tab switch, so animating on mount
/// alone would replay it every time the user came back to Home.
class HomeHero extends StatefulWidget {
  const HomeHero({super.key, this.chatBar, this.animate = true, this.onEntranceComplete});

  /// Optional. Null when the hero is the empty state of a live chat, which
  /// already owns a real composer — the hero is then just the headline.
  final Widget? chatBar;

  /// When false the hero renders in its final state immediately.
  final bool animate;

  /// Fired once the entrance finishes, so the host can suppress replays.
  final VoidCallback? onEntranceComplete;

  @override
  State<HomeHero> createState() => _HomeHeroState();
}

class _HomeHeroState extends State<HomeHero> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  // The headline leads; the bar starts before the headline has finished so the
  // two overlap rather than reading as two separate events.
  static const Interval _headlineCurve = Interval(0.0, 0.62, curve: Curves.easeOutCubic);
  static const Interval _barCurve = Interval(0.38, 1.0, curve: Curves.easeOutCubic);

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: const Duration(milliseconds: 1100));
    if (widget.animate) {
      _controller.forward().whenComplete(() {
        if (mounted) widget.onEntranceComplete?.call();
      });
    } else {
      _controller.value = 1.0;
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  /// Fade plus a short rise. The rise is deliberately small — enough to give the
  /// element somewhere to arrive from, not enough to read as a slide.
  Widget _entrance({required Interval interval, required double rise, required Widget child}) {
    final animation = CurvedAnimation(parent: _controller, curve: interval);
    return AnimatedBuilder(
      animation: animation,
      builder: (context, child) => Opacity(
        opacity: animation.value.clamp(0.0, 1.0),
        child: Transform.translate(offset: Offset(0, rise * (1 - animation.value)), child: child),
      ),
      child: child,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _entrance(
          interval: _headlineCurve,
          rise: 16,
          child: Text(
            'Ask Omi anything about your life',
            textAlign: TextAlign.center,
            style: AppType.headlineMedium.copyWith(height: 1.35),
          ),
        ),
        if (widget.chatBar != null) ...[
          const SizedBox(height: 24),
          _entrance(interval: _barCurve, rise: 20, child: widget.chatBar!),
        ],
      ],
    );
  }
}
