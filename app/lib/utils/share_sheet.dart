import 'package:flutter/widgets.dart';

/// Anchor rect for the system share sheet.
///
/// iPad and macOS present the share sheet as a popover and require a non-zero
/// origin to attach it to. `share_plus` throws a `PlatformException` when the
/// rect is missing or empty, and because share calls are usually the last
/// statement in an async button handler, that exception is unhandled: the sheet
/// never opens and the user sees a button that does nothing.
///
/// Pass the [GlobalKey] of the widget the sheet should appear from. When the key
/// has no laid-out render object — an off-screen anchor, or a caller with no
/// widget to point at — this falls back to a small non-zero rect. Placement is
/// then arbitrary, but the sheet still opens, which is the part that matters.
const Rect kFallbackShareOrigin = Rect.fromLTWH(0, 0, 100, 100);

Rect shareSheetOrigin([GlobalKey? anchorKey]) {
  final box = anchorKey?.currentContext?.findRenderObject() as RenderBox?;
  if (box == null || !box.hasSize || box.size.isEmpty) {
    return kFallbackShareOrigin;
  }
  return box.localToGlobal(Offset.zero) & box.size;
}
