import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class OmiSelectableTile extends AdaptiveWidget {
  final Widget leading;
  final String title;
  final String? subtitle;
  final bool selected;
  final VoidCallback onTap;
  final bool dense;

  const OmiSelectableTile({
    super.key,
    required this.leading,
    required this.title,
    this.subtitle,
    required this.selected,
    required this.onTap,
    this.dense = false,
  });

  @override
  Widget buildDesktop(BuildContext context) => _tile();

  @override
  Widget buildMobile(BuildContext context) => _tile();

  Widget _tile() {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: dense
              ? const EdgeInsets.symmetric(horizontal: 16, vertical: 10)
              : const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
          decoration: BoxDecoration(
            color:
                selected ? ResponsiveHelper.backgroundSecondary : ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: selected
                  ? ResponsiveHelper.purplePrimary.withOpacity(0.5)
                  : ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
              width: 1,
            ),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              // Leading icon/flag/etc.
              SizedBox(width: dense ? 20 : 24, height: dense ? 20 : 24, child: Center(child: leading)),
              const SizedBox(width: 16),
              // Title + subtitle
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      title,
                      style: TextStyle(
                        color: selected ? ResponsiveHelper.textPrimary : ResponsiveHelper.textSecondary,
                        fontSize: 15,
                        fontWeight: selected ? FontWeight.w500 : FontWeight.w400,
                      ),
                    ),
                    if (subtitle != null) ...[
                      const SizedBox(height: 2),
                      Text(
                        subtitle!,
                        style: const TextStyle(
                          color: ResponsiveHelper.textTertiary,
                          fontSize: 13,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: 16),
              // Radio / Check indicator
              Container(
                width: 20,
                height: 20,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: selected ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textTertiary,
                    width: 2,
                  ),
                  color: selected ? ResponsiveHelper.purplePrimary : Colors.transparent,
                ),
                child: selected
                    ? const Icon(
                        Icons.check,
                        color: Colors.white,
                        size: 12,
                      )
                    : null,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
