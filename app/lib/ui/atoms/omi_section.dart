import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/ui/molecules/omi_section_header.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class OmiSection extends AdaptiveWidget {
  final String title;
  final IconData icon;
  final List<Widget> children;
  final EdgeInsetsGeometry? padding;
  final double? borderRadius;

  const OmiSection({
    super.key,
    required this.title,
    required this.icon,
    required this.children,
    this.padding,
    this.borderRadius,
  });

  @override
  Widget buildDesktop(BuildContext context) => _section();

  @override
  Widget buildMobile(BuildContext context) => _section();

  Widget _section() {
    return Container(
      padding: padding ?? const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(borderRadius ?? 16),
        border: Border.all(
          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 15,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          OmiSectionHeader(
            icon: icon,
            title: title,
          ),
          const SizedBox(height: 20),
          ...children,
        ],
      ),
    );
  }
}
