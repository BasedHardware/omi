import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

class BottomNavBar extends StatelessWidget {
  const BottomNavBar({super.key, required this.onTabTap});

  final void Function(int index, bool isRepeat) onTabTap;

  @override
  Widget build(BuildContext context) {
    return Consumer<HomeProvider>(
      builder: (context, home, child) {
        return Align(
          alignment: Alignment.bottomCenter,
          child: Container(
            width: double.infinity,
            height: 100,
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                stops: [0.0, 0.30, 1.0],
                colors: [Colors.transparent, Color.fromARGB(255, 15, 15, 15), Color.fromARGB(255, 15, 15, 15)],
              ),
            ),
            child: Row(
              children: [
                _buildTab(context, home, 0, FontAwesomeIcons.house, 'Home', context.l10n.navHome),
                _buildTab(context, home, 1, FontAwesomeIcons.comments, 'Conversations', context.l10n.navConvos),
                _buildTab(context, home, 2, FontAwesomeIcons.listCheck, 'Tasks', context.l10n.navTodos),
                _buildTab(context, home, 3, FontAwesomeIcons.brain, 'Brain', context.l10n.navBrain),
                _buildTab(context, home, 4, FontAwesomeIcons.tableCellsLarge, 'Apps', context.l10n.apps),
              ],
            ),
          ),
        );
      },
    );
  }

  /// [analyticsLabel] is the stable event name and stays English; [label] is
  /// the localized text rendered under the icon. "Conversations"/"Tasks" keep
  /// their original event names even though the tabs now read Convos/Todos —
  /// renaming the events would break the existing funnel.
  Widget _buildTab(
    BuildContext context,
    HomeProvider home,
    int index,
    FaIconData icon,
    String analyticsLabel,
    String label,
  ) {
    final isSelected = home.selectedIndex == index;
    final color = isSelected ? Colors.white : Colors.grey;
    return Expanded(
      child: InkWell(
        onTap: () {
          HapticFeedback.mediumImpact();
          PlatformManager.instance.analytics.bottomNavigationTabClicked(analyticsLabel);
          primaryFocus?.unfocus();
          onTabTap(index, isSelected);
        },
        child: SizedBox(
          height: 80,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            mainAxisSize: MainAxisSize.min,
            children: [
              FaIcon(icon, color: color, size: 22),
              const SizedBox(height: 6),
              // Long translations (e.g. "Conversaciones") must shrink rather
              // than wrap or overflow the fixed-width tab.
              FittedBox(
                fit: BoxFit.scaleDown,
                child: Text(
                  label,
                  maxLines: 1,
                  style: TextStyle(
                    color: color,
                    fontSize: 11,
                    fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
                    height: 1.0,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
