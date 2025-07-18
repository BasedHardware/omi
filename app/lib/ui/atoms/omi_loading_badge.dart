import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

/// Tiny pill badge that shows a spinner + text. Used for inline loading states
/// such as "Searching…", "Syncing…", etc.
class OmiLoadingBadge extends AdaptiveWidget {
  /// Label displayed next to the spinner.
  final String label;

  /// Accent colour (spinner + border highlight).
  final Color color;

  /// Radius of the badge.
  final double borderRadius;

  /// Padding inside the badge.
  final EdgeInsetsGeometry padding;

  /// Stroke width for the circular progress indicator.
  final double strokeWidth;

  const OmiLoadingBadge({
    super.key,
    this.label = 'Loading…',
    this.color = ResponsiveHelper.purplePrimary,
    this.borderRadius = 6,
    this.padding = const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
    this.strokeWidth = 2,
  });

  @override
  Widget buildDesktop(BuildContext context) => _base();

  @override
  Widget buildMobile(BuildContext context) => _base();

  Widget _base() => Container(
        padding: padding,
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary.withOpacity(0.6),
          borderRadius: BorderRadius.circular(borderRadius),
          border: Border.all(color: color.withOpacity(0.3), width: 1),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 12,
              height: 12,
              child: CircularProgressIndicator(
                strokeWidth: strokeWidth,
                valueColor: AlwaysStoppedAnimation<Color>(color.withOpacity(0.8)),
              ),
            ),
            const SizedBox(width: 8),
            Text(
              label,
              style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w500,
                color: ResponsiveHelper.textSecondary,
              ),
            ),
          ],
        ),
      );
}
