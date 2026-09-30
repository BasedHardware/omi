import 'dart:async';
import 'dart:ui';

import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_button.dart';
import 'package:omi/ui/omi_tokens.dart';

/// A frosted card preview with one readable action above its obscured content.
class OmiLockedPreview extends StatelessWidget {
  const OmiLockedPreview({
    super.key,
    required this.child,
    required this.label,
    required this.onPressed,
  });

  final Widget child;
  final String label;
  final FutureOr<void> Function() onPressed;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: OmiRadius.xlAll,
      child: Stack(
        alignment: Alignment.center,
        children: [
          ExcludeSemantics(
            child: IgnorePointer(
              // Filter only this card's content, not the scrolling backdrop.
              child: ImageFiltered(imageFilter: ImageFilter.blur(sigmaX: 6, sigmaY: 6), child: child),
            ),
          ),
          Positioned.fill(child: ColoredBox(color: OmiColors.surface1.withValues(alpha: 0.35))),
          // Non-positioned so the action can also determine the card's height.
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
            child: OmiButton(
              key: const Key('locked_preview_action'),
              label: label,
              icon: Icons.lock_outline,
              size: OmiButtonSize.compact,
              onPressed: onPressed,
            ),
          ),
        ],
      ),
    );
  }
}
