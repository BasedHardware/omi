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
