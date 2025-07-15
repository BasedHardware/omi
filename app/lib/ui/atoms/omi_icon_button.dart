import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

enum OmiIconButtonStyle { filled, outline, neutral }

class OmiIconButton extends AdaptiveWidget {
  final IconData icon;
  final VoidCallback? onPressed;
  final OmiIconButtonStyle style;
  final double size;
  final double iconSize;
  final Color? color;
  final bool solid;
  final double borderRadius;
  final double borderOpacity;

  const OmiIconButton({
    super.key,
    required this.icon,
    required this.onPressed,
    this.style = OmiIconButtonStyle.filled,
    this.size = 44,
    this.iconSize = 20,
    this.color,
    this.solid = false,
    this.borderRadius = 12,
    this.borderOpacity = 0.3,
  });

  @override
  Widget buildDesktop(BuildContext context) => _base(context);

  @override
  Widget buildMobile(BuildContext context) => _base(context);

  Widget _base(BuildContext context) {
    final filled = style == OmiIconButtonStyle.filled;
    final neutral = style == OmiIconButtonStyle.neutral;
    final baseColor = color ?? (filled ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary);

    final bgColor = neutral
        ? ResponsiveHelper.backgroundTertiary.withOpacity(0.6)
        : filled
            ? (solid ? baseColor : baseColor.withOpacity(0.15))
            : Colors.transparent;

    final iconColor = neutral
        ? ResponsiveHelper.textSecondary
        : filled
            ? (solid ? Colors.white : baseColor)
            : baseColor;

    final border =
        style == OmiIconButtonStyle.outline ? Border.all(color: baseColor.withOpacity(borderOpacity), width: 1) : null;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(borderRadius),
        child: Container(
          height: size,
          width: size,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: bgColor,
            borderRadius: BorderRadius.circular(borderRadius),
            border: border,
          ),
          child: Icon(
            icon,
            color: iconColor,
            size: iconSize,
          ),
        ),
      ),
    );
  }
}
