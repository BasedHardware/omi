import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';

/// A small tinted pill action on a sync status card ("Sync", "Cancel"). The painted pill is compact;
/// the touch target is at least 44pt tall and the pill is announced as a button.
Widget statusActionPill(String label, Color color, VoidCallback onTap) {
  return Semantics(
    button: true,
    child: GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: kOmiMinTapTarget, minWidth: kOmiMinTapTarget),
        child: Center(
          widthFactor: 1,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
            decoration: BoxDecoration(color: color.withValues(alpha: 0.15), borderRadius: OmiRadius.pillAll),
            child: Text(label, style: OmiType.footnote.copyWith(color: color, fontWeight: FontWeight.w500)),
          ),
        ),
      ),
    ),
  );
}
