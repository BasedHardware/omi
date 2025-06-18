import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

enum OmiIconButtonStyle { filled, outline }

class OmiIconButton extends AdaptiveWidget {
  final IconData icon;
  final VoidCallback? onPressed;
  final OmiIconButtonStyle style;
  final double size;
  final Color? color;

  const OmiIconButton({
    super.key,
    required this.icon,
    required this.onPressed,
    this.style = OmiIconButtonStyle.filled,
    this.size = 44,
    this.color,
  });

  @override
  Widget buildDesktop(BuildContext context) => _base(context);

  @override
  Widget buildMobile(BuildContext context) => _base(context);

  Widget _base(BuildContext context) {
    final filled = style == OmiIconButtonStyle.filled;
    final baseColor = color ?? (filled ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary);

    final bgColor = filled
        ? baseColor.withOpacity(0.15)
        : ResponsiveHelper.backgroundTertiary.withOpacity(0.6);

    final iconColor = filled ? baseColor : baseColor;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          height: size,
          width: size,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: bgColor,
            borderRadius: BorderRadius.circular(12),
            border: filled ? null : Border.all(color: baseColor.withOpacity(0.3), width: 1),
          ),
          child: Icon(
            icon,
            color: iconColor,
            size: 20,
          ),
        ),
      ),
    );
  }
} 