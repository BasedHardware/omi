import 'package:flutter/material.dart';

/// Tallest a bottom-anchored onboarding step block may be.
///
/// The wrapper's persistent backdrops — the device + glow behind splash,
/// sign-in and data & privacy, and the dot ring behind the later steps — are
/// centred just above the vertical midpoint and reach down to roughly half
/// the screen height. A step's text and buttons rise from the bottom, so
/// anything taller than the lower half climbs into the artwork. Cap the block
/// here and scroll inside it instead.
double onboardingBottomBlockMaxHeight(BuildContext context) {
  final size = MediaQuery.sizeOf(context);
  return size.height * 0.5 - 8;
}

/// Sizes a bottom-block's copy to the height it is given instead of
/// scrolling it: at its natural size when it fits, scaled down uniformly
/// (text, spacing and tiles together) when it does not, so the block never
/// climbs into the artwork and never needs to scroll. Wrap the copy only —
/// buttons stay outside at full size.
class OnboardingFitToHeight extends StatelessWidget {
  final Widget child;

  const OnboardingFitToHeight({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        return FittedBox(
          fit: BoxFit.scaleDown,
          alignment: Alignment.bottomCenter,
          child: SizedBox(width: constraints.maxWidth, child: child),
        );
      },
    );
  }
}
