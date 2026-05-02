import 'dart:ui';

import 'package:flutter/material.dart';

import 'package:nooto_v2/theme/app_theme.dart';

/// Pill-style sub-tab row for the Library shell. Mirrors desktop-v2's
/// `SectionTabBar` (icon + label, filled active pill) with iOS 26 Liquid
/// Glass dressing — translucent tint over a BackdropFilter blur — so it
/// reads as a header strip continuous with the AppBar above it.
class LibrarySectionTabBar<T> extends StatelessWidget {
  const LibrarySectionTabBar({
    super.key,
    required this.tabs,
    required this.active,
    required this.onChanged,
  });

  final List<LibrarySectionTab<T>> tabs;
  final T active;
  final ValueChanged<T> onChanged;

  /// Approximate height of this strip (icon-pill + vertical padding). Used
  /// by the Library shell to pad scrollable content so the first row
  /// doesn't render under the bar at rest.
  static const double height = 44.0;

  @override
  Widget build(BuildContext context) {
    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
        child: DecoratedBox(
          decoration: const BoxDecoration(
            color: Color(0x8C0F0F0F), // backgroundPrimary @ ~55% over blur
            border: Border(
              bottom: BorderSide(color: Color(0x14FFFFFF), width: 0.5),
            ),
          ),
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(
              horizontal: AppStyles.spacingL,
              vertical: AppStyles.spacingS,
            ),
            child: Row(
              children: [
                for (final t in tabs) ...[
                  _Pill(
                    tab: t,
                    active: t.id == active,
                    onTap: () => onChanged(t.id),
                  ),
                  const SizedBox(width: AppStyles.spacingXS),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class LibrarySectionTab<T> {
  const LibrarySectionTab({required this.id, required this.label, required this.icon});
  final T id;
  final String label;
  final IconData icon;
}

class _Pill extends StatelessWidget {
  const _Pill({required this.tab, required this.active, required this.onTap});
  final LibrarySectionTab tab;
  final bool active;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final fg = active ? AppColors.backgroundPrimary : AppColors.textSecondary;
    final bg = active ? AppColors.textPrimary : Colors.transparent;
    return Semantics(
      button: true,
      selected: active,
      label: tab.label,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(AppStyles.radiusPill),
          child: Container(
            padding: const EdgeInsets.symmetric(
              horizontal: AppStyles.spacingM,
              vertical: 6,
            ),
            decoration: BoxDecoration(
              color: bg,
              borderRadius: BorderRadius.circular(AppStyles.radiusPill),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(tab.icon, size: 14, color: fg),
                const SizedBox(width: 6),
                Text(
                  tab.label,
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                    color: fg,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
