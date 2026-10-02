import 'package:flutter/widgets.dart';

import 'omi_tokens.dart';

/// Marks a screen that paints the canvas: a white page with cards in the grouped grey in light mode,
/// the usual surfaces in dark. Home, Tasks and the conversation page wrap their body in it; every
/// other screen keeps the grouped look (a [OmiColors.surface0] page with [OmiColors.surface1] cards).
///
/// A widget that can sit on either kind of page reads its colours through [pageOf] and [cardOf]
/// instead of naming a surface, so it stays visible on both.
class OmiCanvas extends InheritedWidget {
  const OmiCanvas({super.key, required super.child});

  /// Whether [context] is on a canvas screen. A plain lookup: the marker never changes, so callers
  /// need no rebuild dependency on it.
  static bool isOn(BuildContext context) => context.getInheritedWidgetOfExactType<OmiCanvas>() != null;

  /// The page colour under [context].
  static Color pageOf(BuildContext context) => isOn(context) ? OmiColors.canvas : OmiColors.surface0;

  /// The fill of a card on that page.
  static Color cardOf(BuildContext context) => isOn(context) ? OmiColors.canvasCard : OmiColors.surface1;

  @override
  bool updateShouldNotify(OmiCanvas oldWidget) => false;
}
