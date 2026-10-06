import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';

// Chat is drawn in two colours: the ink and the canvas. The user's message is a solid pill in the
// accent (see `user_message.dart`); Omi's answer is text on the page with no box; everything else
// (a control, a card inside an answer, a hairline) is the ink at an opacity, the way iOS draws its
// fills, never an outline.

/// The chat's materials: the ink at an opacity.
abstract final class ChatInk {
  static bool get _dark => OmiColors.active == OmiPalette.dark;

  /// A control or a card inside an answer, with no edge.
  static Color get fill => OmiColors.textPrimary.withValues(alpha: _dark ? 0.10 : 0.055);

  /// A control that sits on [fill] (the app pill in the composer).
  static Color get fill2 => OmiColors.textPrimary.withValues(alpha: _dark ? 0.16 : 0.09);

  /// The line between source rows.
  static Color get sep => OmiColors.textPrimary.withValues(alpha: _dark ? 0.12 : 0.09);
}

/// The look of a card inside an answer (a task, a chart, a failed reply) and of the starters.
abstract final class ChatInsetCard {
  static BoxDecoration decoration({BorderRadius radius = OmiRadius.lgAll}) =>
      BoxDecoration(color: ChatInk.fill, borderRadius: radius);
}
