import 'package:flutter/material.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

/// Reusable empty-state widget used across pages and drawers.
///
/// Provides a large icon, title and optional subtitle message.
class OmiEmptyState extends StatelessWidget {
  /// Icon to display inside the coloured bubble.
  final IconData icon;

  /// Title text shown below the icon.
  final String title;

  /// Optional subtitle/description.
  final String? message;

  /// Icon and accent colour (also used as background with low opacity).
  final Color color;

  /// Size of the icon.
  final double iconSize;

  /// Padding around the icon bubble.
  final double iconPadding;

  const OmiEmptyState({
    super.key,
    required this.icon,
    required this.title,
    this.message,
    this.color = ResponsiveHelper.purplePrimary,
    this.iconSize = 48,
    this.iconPadding = 20,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        padding: EdgeInsets.all(iconPadding),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Icon bubble.
            Container(
              padding: EdgeInsets.all(iconPadding),
              decoration: BoxDecoration(
                color: color.withOpacity(0.2),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Icon(
                icon,
                size: iconSize,
                color: color,
              ),
            ),
            const SizedBox(height: 24),
            Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: ResponsiveHelper.textPrimary,
                fontSize: 18,
                fontWeight: FontWeight.w600,
              ),
            ),
            if (message != null) ...[
              const SizedBox(height: 8),
              Text(
                message!,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: ResponsiveHelper.textSecondary,
                  fontSize: 14,
                  height: 1.5,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
