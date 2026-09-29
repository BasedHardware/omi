import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';

import 'package:omi/providers/home_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Home and Tasks as two large words at the top of the shell; the selected one is in full ink, the
/// other muted. It replaces the bottom tab bar. [trailing] holds the selected page's own actions.
class HomeTabSwitcher extends StatelessWidget {
  const HomeTabSwitcher({super.key, required this.onTabTap, this.trailing});

  /// [isRepeat] is true when the tapped tab is already selected (scroll it to the top).
  final void Function(int index, bool isRepeat) onTabTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final selected = context.select<HomeProvider, int>((home) => home.selectedIndex);
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.sm, OmiSpacing.xxs),
      child: Row(
        children: [
          _tab(context, selected, HomeProvider.homeTab, l10n.home, 'Home'),
          const SizedBox(width: OmiSpacing.md),
          _tab(context, selected, HomeProvider.tasksTab, l10n.tasks, 'Tasks'),
          const Spacer(),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }

  /// [analyticsName] is the stable event name; [label] is what the reader sees and hears.
  Widget _tab(BuildContext context, int selected, int index, String label, String analyticsName) {
    final isSelected = selected == index;
    return Semantics(
      button: true,
      selected: isSelected,
      label: label,
      excludeSemantics: true,
      child: GestureDetector(
        key: ValueKey('home_tab_$analyticsName'),
        behavior: HitTestBehavior.opaque,
        onTap: () {
          onTabTap(index, isSelected);
          primaryFocus?.unfocus();
          WidgetsBinding.instance.addPostFrameCallback((_) {
            HapticFeedback.selectionClick();
            PlatformManager.instance.analytics.bottomNavigationTabClicked(analyticsName);
          });
        },
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: kOmiMinTapTarget),
          child: Align(
            alignment: Alignment.centerLeft,
            widthFactor: 1,
            child: AnimatedDefaultTextStyle(
              duration: const Duration(milliseconds: 180),
              curve: Curves.easeOut,
              style: OmiType.title1.copyWith(color: isSelected ? OmiColors.textPrimary : OmiColors.textTertiary),
              child: Text(label),
            ),
          ),
        ),
      ),
    );
  }
}
