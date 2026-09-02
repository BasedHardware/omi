import 'package:flutter/material.dart';

/// Wraps onboarding step content so each step fades and slides up into place
/// when the flow advances to a new page, instead of cutting abruptly between
/// screens. Swap the `child`/`pageKey` (e.g. to the current TabController
/// index) to trigger the transition.
class OnboardingPageTransition extends StatelessWidget {
  final Object pageKey;
  final Widget child;
  final Duration duration;

  const OnboardingPageTransition({
    super.key,
    required this.pageKey,
    required this.child,
    this.duration = const Duration(milliseconds: 420),
  });

  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: duration,
      switchInCurve: Curves.easeOutCubic,
      switchOutCurve: Curves.easeInCubic,
      transitionBuilder: (widgetChild, animation) {
        final slide = Tween<Offset>(begin: const Offset(0, 0.04), end: Offset.zero).animate(animation);
        return FadeTransition(
          opacity: animation,
          child: SlideTransition(position: slide, child: widgetChild),
        );
      },
      layoutBuilder: (currentChild, previousChildren) {
        return Stack(
          alignment: Alignment.center,
          children: [...previousChildren, if (currentChild != null) currentChild],
        );
      },
      child: KeyedSubtree(key: ValueKey(pageKey), child: child),
    );
  }
}
