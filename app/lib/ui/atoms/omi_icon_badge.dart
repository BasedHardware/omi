import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';

class OmiIconBadge extends AdaptiveWidget {
  final IconData icon;
  final Color bgColor;
  final Color iconColor;
  final double iconSize;
  final double radius;
  final EdgeInsets padding;
  const OmiIconBadge({
    super.key,
    required this.icon,
    required this.bgColor,
    required this.iconColor,
    this.iconSize = 16,
    this.radius = 8,
    this.padding = const EdgeInsets.all(8),
  });

  @override
  Widget buildDesktop(BuildContext context) => _base();

  @override
  Widget buildMobile(BuildContext context) => _base();

  Widget _base() {
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(radius),
      ),
      child: Icon(
        icon,
        color: iconColor,
        size: iconSize,
      ),
    );
  }
}
