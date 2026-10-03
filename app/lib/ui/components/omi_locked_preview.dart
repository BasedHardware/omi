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
    this.interactive = false,
  });

  final Widget child;
  final String label;
  final FutureOr<void> Function() onPressed;

  /// Lets gestures reach the obscured [child] (for example a row's long-press menu or swipe). The
  /// content stays blurred and hidden from semantics; only the tint stops absorbing touches.
  final bool interactive;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: OmiRadius.xlAll,
      child: Stack(
        alignment: Alignment.center,
        children: [
          ExcludeSemantics(
            child: IgnorePointer(
              ignoring: !interactive,
              // Filter only this card's content, not the scrolling backdrop.
              child: ImageFiltered(
                imageFilter: ImageFilter.blur(sigmaX: 6, sigmaY: 6),
                // This obscured content is decorative. The readable action below
                // keeps the user's text scale and determines its own height.
                child: MediaQuery.withNoTextScaling(child: child),
              ),
            ),
          ),
          Positioned.fill(
            child: IgnorePointer(
              ignoring: interactive,
              child: ColoredBox(
                key: const Key('locked_preview_tint'),
                color: OmiColors.surface1.withValues(alpha: 0.65),
              ),
            ),
          ),
          // Non-positioned so the action can also determine the card's height.
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
            child: OmiButton.tertiary(
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
