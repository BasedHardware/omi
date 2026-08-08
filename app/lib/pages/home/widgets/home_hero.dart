import 'package:flutter/material.dart';

// Still imported for the commented-out ramp-based headline below.
// ignore: unused_import
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
      builder: (context, child) {
        final t = animation.value.clamp(0.0, 1.0);
        // Drop the wrapper once settled rather than leaving an Opacity(1.0) and
        // an identity Transform in the tree for the rest of the session.
        if (t >= 1.0) return child!;
        return Opacity(
          opacity: t,
          child: Transform.translate(offset: Offset(0, rise * (1 - t)), child: child),
        );
      },
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
          // Headline, styled inline rather than through the type ramp. The
          // ramp-based version below rendered measurably grey on device
          // (peak 190/255 against 255 for the app bar's own white text) and
          // none of colour, tracking, the entrance fade, or the layer tree
          // accounted for it. Kept commented rather than deleted so the
          // comparison is still there when the cause is found.
          child: const Text(
            'Ask Omi anything about your life',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: Color(0xFFFFFFFF),
              fontSize: 20,
              fontWeight: FontWeight.w600,
              // No fractional line height. A `height` of 1.35 put the baseline
              // on a sub-pixel offset, and the vertical antialiasing that
              // caused dulled the glyphs to ~194/255 — the headline read grey
              // beside the app bar's own white text. It's a single line, so
              // there is no leading to set anyway.
            ),
          ),
          // child: Text(
          //   'Ask Omi anything about your life',
          //   textAlign: TextAlign.center,
          //   style: AppType.headlineMedium.copyWith(
          //     height: 1.35,
          //     letterSpacing: 0,
          //     color: Colors.white,
          //   ),
          // ),
        ),
        if (widget.chatBar != null) ...[
          const SizedBox(height: 24),
          _entrance(interval: _barCurve, rise: 20, child: widget.chatBar!),
        ],
      ],
    );
  }
}
