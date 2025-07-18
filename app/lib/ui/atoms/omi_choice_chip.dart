import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class OmiChoiceChip extends AdaptiveWidget {
  final bool selected;
  final VoidCallback onTap;
  final String label;
  final IconData? icon;
  final bool expand;
  const OmiChoiceChip({
    super.key,
    required this.selected,
    required this.onTap,
    required this.label,
    this.icon,
    this.expand = false,
  });

  @override
  Widget buildDesktop(BuildContext context) => _chip();

  @override
  Widget buildMobile(BuildContext context) => _chip();

  Widget _chip() {
    final Widget content = Row(
      mainAxisSize: expand ? MainAxisSize.max : MainAxisSize.min,
      children: [
        if (icon != null) ...[
          Icon(
            icon,
            size: 16,
            color: selected ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
          ),
          const SizedBox(width: 6),
        ],
        Flexible(
          child: Text(
            label,
            style: TextStyle(
              color: selected ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
              fontSize: 12,
              fontWeight: selected ? FontWeight.w500 : FontWeight.w400,
            ),
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ],
    );

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: expand ? const EdgeInsets.all(12) : const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: selected
                ? ResponsiveHelper.purplePrimary.withOpacity(0.2)
                : ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: selected ? ResponsiveHelper.purplePrimary : ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
              width: 1,
            ),
          ),
          child: expand ? Column(crossAxisAlignment: CrossAxisAlignment.start, children: [content]) : content,
        ),
      ),
    );
  }
}
