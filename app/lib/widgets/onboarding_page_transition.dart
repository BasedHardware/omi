import 'dart:async';

import 'package:flutter/material.dart';

/// Wraps onboarding step content so each step slowly fades out and fades
/// back in when the flow advances to a new page, instead of cutting
/// abruptly between screens. Swap the `child`/`pageKey` (e.g. to the current
/// TabController index) to trigger the transition.
class OnboardingPageTransition extends StatelessWidget {
  final Object pageKey;
  final Widget child;
  final Duration duration;

  // Holds the incoming page invisible for this long before its own fade-in
  // starts — used when a backdrop behind it (e.g. the spinner) needs to
  // finish fading out first, so the two never visibly overlap.
  final Duration entryDelay;

  const OnboardingPageTransition({
    super.key,
    required this.pageKey,
    required this.child,
    this.duration = const Duration(milliseconds: 700),
    this.entryDelay = Duration.zero,
  });

  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: duration,
      switchInCurve: Curves.easeIn,
      switchOutCurve: Curves.easeOut,
      transitionBuilder: (widgetChild, animation) {
        return FadeTransition(opacity: animation, child: widgetChild);
      },
      layoutBuilder: (currentChild, previousChildren) {
        return Stack(
          alignment: Alignment.center,
          children: [...previousChildren, if (currentChild != null) currentChild],
        );
      },
      child: KeyedSubtree(
        key: ValueKey(pageKey),
        // Always wrap, even when [entryDelay] is zero. Swapping this child
        // between a delayed fade and the raw page remounts the step — on
        // speech profile that re-ran close() after Get Started and looped
        // back to "please find a quiet place".
        child: _DelayedFadeIn(delay: entryDelay, duration: duration, child: child),
      ),
    );
  }
}

/// Stays fully transparent for [delay], then fades in over [duration] —
/// independent of any enclosing AnimatedSwitcher transition, whose own fade
/// may finish well before [delay] elapses.
class _DelayedFadeIn extends StatefulWidget {
  final Duration delay;
  final Duration duration;
  final Widget child;

  const _DelayedFadeIn({required this.delay, required this.duration, required this.child});

  @override
  State<_DelayedFadeIn> createState() => _DelayedFadeInState();
}

class _DelayedFadeInState extends State<_DelayedFadeIn> {
  bool _visible = false;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    if (widget.delay == Duration.zero) {
      _visible = true;
      return;
    }
    _timer = Timer(widget.delay, () {
      if (mounted) setState(() => _visible = true);
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  void didUpdateWidget(_DelayedFadeIn oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.delay == Duration.zero && !_visible) {
      _timer?.cancel();
      _visible = true;
    }
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedOpacity(
      opacity: _visible ? 1 : 0,
      duration: widget.duration,
      curve: Curves.easeIn,
      child: widget.child,
    );
  }
}
