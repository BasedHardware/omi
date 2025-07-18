import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class OmiPopupMenuButton<T> extends AdaptiveWidget {
  final List<PopupMenuEntry<T>> Function(BuildContext) itemBuilder;
  final void Function(T)? onSelected;
  final IconData? icon;
  final Widget? child;
  const OmiPopupMenuButton({
    super.key,
    required this.itemBuilder,
    this.icon,
    this.child,
    this.onSelected,
  });

  @override
  Widget buildDesktop(BuildContext context) => _base(context);

  @override
  Widget buildMobile(BuildContext context) => _base(context);

  Widget _base(BuildContext context) {
    return PopupMenuButton<T>(
      color: ResponsiveHelper.backgroundSecondary,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      itemBuilder: itemBuilder,
      onSelected: onSelected,
      child: child ??
          Container(
            padding: const EdgeInsets.all(6),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(
              icon ?? Icons.more_vert,
              color: ResponsiveHelper.textSecondary,
              size: 16,
            ),
          ),
    );
  }
}
