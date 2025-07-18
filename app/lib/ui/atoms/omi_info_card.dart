import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class OmiInfoCard extends AdaptiveWidget {
  final List<Widget> children;
  final EdgeInsetsGeometry? padding;
  final double? borderRadius;
  final Color? backgroundColor;
  final Color? borderColor;
  final List<BoxShadow>? shadows;

  const OmiInfoCard({
    super.key,
    required this.children,
    this.padding,
    this.borderRadius,
    this.backgroundColor,
    this.borderColor,
    this.shadows,
  });

  @override
  Widget buildDesktop(BuildContext context) => _card();

  @override
  Widget buildMobile(BuildContext context) => _card();

  Widget _card() {
    return Container(
      padding: padding ?? const EdgeInsets.all(32),
      decoration: BoxDecoration(
        color: backgroundColor ?? ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.8),
        borderRadius: BorderRadius.circular(borderRadius ?? 20),
        border: Border.all(
          color: borderColor ?? ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
          width: 1,
        ),
        boxShadow: shadows ??
            [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.1),
                blurRadius: 20,
                offset: const Offset(0, 8),
              ),
            ],
      ),
      child: Column(
        children: children,
      ),
    );
  }
}
