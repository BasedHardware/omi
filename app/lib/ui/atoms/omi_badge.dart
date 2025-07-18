import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class OmiBadge extends AdaptiveWidget {
  final String label;
  final Color color;
  final double fontSize;
  final EdgeInsetsGeometry padding;
  final double borderRadius;
  final Color? backgroundColor;
  const OmiBadge({
    super.key,
    required this.label,
    this.color = ResponsiveHelper.purplePrimary,
    this.fontSize = 10,
    this.padding = const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
    this.borderRadius = 6,
    this.backgroundColor,
  });

  @override
  Widget buildDesktop(BuildContext context) => _base();

  @override
  Widget buildMobile(BuildContext context) => _base();

  Widget _base() => Container(
        padding: padding,
        decoration: BoxDecoration(
          color: backgroundColor ?? color.withOpacity(0.15),
          borderRadius: BorderRadius.circular(borderRadius),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: color,
            fontSize: fontSize,
            fontWeight: FontWeight.w500,
          ),
        ),
      );
}
