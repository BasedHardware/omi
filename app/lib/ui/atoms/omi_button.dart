import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

enum OmiButtonType { primary, text, neutral }

class OmiButton extends AdaptiveWidget {
  final String label;
  final VoidCallback? onPressed;
  final OmiButtonType type;
  final bool enabled;
  final IconData? icon;
  final Color? color;

  const OmiButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.type = OmiButtonType.primary,
    this.enabled = true,
    this.icon,
    this.color,
  });

  @override
  Widget buildDesktop(BuildContext context) => _base();

  @override
  Widget buildMobile(BuildContext context) => _base();

  Widget _base() {
    switch (type) {
      case OmiButtonType.text:
        return TextButton(
          onPressed: enabled ? onPressed : null,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (icon != null) ...[
                Icon(icon, size: 18, color: enabled ? ResponsiveHelper.textSecondary : ResponsiveHelper.textTertiary),
                const SizedBox(width: 4),
              ],
              Text(
                label,
                style: TextStyle(
                  color: enabled ? ResponsiveHelper.textSecondary : ResponsiveHelper.textTertiary,
                  fontSize: 14,
                ),
              ),
            ],
          ),
        );
      case OmiButtonType.primary:
        final primaryColor = color ?? ResponsiveHelper.purplePrimary;
        final primaryAccent = color ?? ResponsiveHelper.purpleAccent;

        return Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: enabled ? onPressed : null,
            borderRadius: BorderRadius.circular(12),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
              decoration: BoxDecoration(
                gradient: enabled
                    ? LinearGradient(
                        colors: [primaryColor, primaryAccent],
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                      )
                    : LinearGradient(
                        colors: [ResponsiveHelper.backgroundTertiary, ResponsiveHelper.backgroundTertiary]),
                borderRadius: BorderRadius.circular(12),
                boxShadow: enabled
                    ? [
                        BoxShadow(
                          color: primaryColor.withOpacity(0.3),
                          blurRadius: 8,
                          offset: const Offset(0, 4),
                        ),
                      ]
                    : null,
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (icon != null) ...[
                    Icon(icon, size: 18, color: Colors.white),
                    const SizedBox(width: 6),
                  ],
                  Text(
                    label,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      case OmiButtonType.neutral:
        return Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: enabled ? onPressed : null,
            borderRadius: BorderRadius.circular(8),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (icon != null) ...[
                    Icon(icon,
                        size: 12, color: enabled ? ResponsiveHelper.textSecondary : ResponsiveHelper.textQuaternary),
                    const SizedBox(width: 6),
                  ],
                  Text(
                    label,
                    style: TextStyle(
                      color: enabled ? ResponsiveHelper.textSecondary : ResponsiveHelper.textQuaternary,
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
    }
  }
}
