import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_glass.dart';
import 'package:omi/ui/omi_tokens.dart';

/// The v2 toolbar group: a page's header actions side by side in one glass capsule (map and sync
/// on Conversations, export and completed on Tasks). Each child is a 44pt [OmiIconButton] or
/// similar; the capsule adds no padding of its own around their targets.
class OmiToolbarCapsule extends StatelessWidget {
  const OmiToolbarCapsule({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    if (children.isEmpty) return const SizedBox.shrink();
    return OmiGlass(
      inHeader: true,
      borderRadius: OmiRadius.pillAll,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxs),
        child: Row(mainAxisSize: MainAxisSize.min, children: children),
      ),
    );
  }
}

/// A labelled glass capsule in a toolbar (v2 "Select").
class OmiToolbarTextButton extends StatelessWidget {
  const OmiToolbarTextButton({super.key, required this.label, required this.onPressed});

  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      enabled: onPressed != null,
      label: label,
      excludeSemantics: true,
      onTap: onPressed,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onPressed,
        child: OmiGlass(
          inHeader: true,
          borderRadius: OmiRadius.pillAll,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: OmiSize.minTap),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
              child: Center(
                widthFactor: 1,
                child: Text(label, style: OmiType.headline),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
