import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';

/// Height of the navigation row (progress dots and back button) below the status bar: the dots'
/// top gap plus one tap target.
const double kOnboardingChromeHeight = OmiSpacing.md + kOmiMinTapTarget;

/// The host owns space for navigation above steps that start at the top of the screen.
/// Bottom-card steps keep their navigation over the background artwork, but their content still
/// clears it: the step gets a [MediaQuery] whose top padding includes [kOnboardingChromeHeight], so
/// its own [SafeArea] starts below the navigation while backgrounds bleed to the top edge.
class OnboardingStepLayout extends StatelessWidget {
  const OnboardingStepLayout({super.key, required this.child, required this.reserveHeader, this.progress, this.onBack});

  final Widget child;
  final bool reserveHeader;
  final Widget? progress;
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context) {
    final chrome = Stack(
      children: [
        if (progress != null)
          Padding(
            padding: const EdgeInsets.only(top: OmiSpacing.md),
            child: progress!,
          ),
        if (onBack != null)
          Padding(
            padding: const EdgeInsets.only(left: OmiSpacing.xs, top: OmiSpacing.xxs),
            child: Align(
              alignment: Alignment.topLeft,
              child: OmiBackButton.circled(key: const Key('onboarding_back'), onPressed: onBack),
            ),
          ),
      ],
    );
    if (reserveHeader) {
      return Column(
        children: [
          SafeArea(
            bottom: false,
            child: SizedBox(height: kOnboardingChromeHeight, child: chrome),
          ),
          Expanded(
            child: MediaQuery.removePadding(context: context, removeTop: true, child: child),
          ),
        ],
      );
    }
    if (progress == null && onBack == null) return child;
    final media = MediaQuery.of(context);
    return Stack(
      children: [
        MediaQuery(
          data: media.copyWith(padding: media.padding.copyWith(top: media.padding.top + kOnboardingChromeHeight)),
          child: child,
        ),
        SafeArea(child: chrome),
      ],
    );
  }
}
