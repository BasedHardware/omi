import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';

import 'package:omi/providers/home_provider.dart';
import 'package:omi/services/dev_controls/addressability_catalog.dart';
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
          // Conversations live in Home now, so the catalogued Conversations control is the Home tab.
          KeyedSubtree(
            key: OmiKeys.homeTabConversations,
            child: _tab(context, selected, HomeProvider.homeTab, l10n.home, 'Home', OmiKeys.homeTabHome),
          ),
          const SizedBox(width: OmiSpacing.sm),
          _tab(context, selected, HomeProvider.tasksTab, l10n.tasks, 'Tasks', OmiKeys.homeTabTasks),
          const Spacer(),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }

  /// [analyticsName] is the stable event name; [label] is what the reader sees and hears.
  Widget _tab(BuildContext context, int selected, int index, String label, String analyticsName, Key key) {
    final isSelected = selected == index;
    void select() {
      onTabTap(index, isSelected);
      primaryFocus?.unfocus();
      WidgetsBinding.instance.addPostFrameCallback((_) {
        HapticFeedback.selectionClick();
        PlatformManager.instance.analytics.bottomNavigationTabClicked(analyticsName);
      });
    }

    // excludeSemantics hides the detector's own tap action, so the node carries it explicitly.
    return Semantics(
      button: true,
      selected: isSelected,
      label: label,
      excludeSemantics: true,
      onTap: select,
      child: GestureDetector(
        key: key,
        behavior: HitTestBehavior.opaque,
        onTap: select,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: kOmiMinTapTarget),
          child: Align(
            alignment: Alignment.centerLeft,
            widthFactor: 1,
            child: AnimatedDefaultTextStyle(
              duration: const Duration(milliseconds: 180),
              curve: Curves.easeOut,
              style: OmiType.title2.copyWith(
                  fontWeight: FontWeight.w700, color: isSelected ? OmiColors.textPrimary : OmiColors.textTertiary),
              child: Text(label),
            ),
          ),
        ),
      ),
    );
  }
}
