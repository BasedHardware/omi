import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/theme/app_theme.dart';
import 'package:omi/utils/ui_guidelines.dart';

/// A reusable header icon button that complies with Apple HIG touch target requirements.
/// Minimum size is 44x44pt as per Apple Human Interface Guidelines.
class HeaderIconButton extends StatelessWidget {
  final Widget icon;
  final VoidCallback? onPressed;
  final Color? backgroundColor;
  final bool isActive;
  final Color? activeBackgroundColor;
  final EdgeInsets? margin;

  /// Apple HIG minimum touch target size
  static const double size = AppStyles.touchTargetMinimum;

  const HeaderIconButton({
    super.key,
    required this.icon,
    this.onPressed,
    this.backgroundColor,
    this.isActive = false,
    this.activeBackgroundColor,
    this.margin,
  });

  @override
  Widget build(BuildContext context) {
    final bgColor = isActive
        ? (activeBackgroundColor ?? context.primaryColor.withValues(alpha: 0.5))
        : (backgroundColor ?? const Color(0xFF1F1F25));

    return Container(
      width: size,
      height: size,
      margin: margin,
      decoration: BoxDecoration(
        color: bgColor,
        shape: BoxShape.circle,
      ),
      child: IconButton(
        padding: EdgeInsets.zero,
        onPressed: onPressed != null
            ? () {
                HapticFeedback.mediumImpact();
                onPressed!();
              }
            : null,
        icon: icon,
      ),
    );
  }
}
