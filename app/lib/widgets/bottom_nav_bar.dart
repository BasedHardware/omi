import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The bar's opaque fill — very slightly lifted off pure black so the divider
/// above it has something to sit against.
const Color _navSurface = Color.fromARGB(255, 15, 15, 15);

/// Hairline separating the bar from the page. 0.5 logical px renders as a true
/// hairline on 2x/3x screens; a neutral white at low alpha rather than a fixed
/// grey so it holds up if the surface beneath it ever changes.
const Color _navDivider = Color(0x14FFFFFF);

class BottomNavBar extends StatelessWidget {
  const BottomNavBar({super.key, required this.onTabTap});

  final void Function(int index, bool isRepeat) onTabTap;

  @override
  Widget build(BuildContext context) {
    return Consumer<HomeProvider>(
      builder: (context, home, child) {
        return Align(
          alignment: Alignment.bottomCenter,
          // Split into a scrim strip and a solid bar so the divider can sit
          // exactly where the fill turns opaque. The whole thing still measures
          // 100 — 20 of scrim over an 80 bar — so the tabs land where they
          // always did.
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Content scrolling up to the bar fades out instead of being cut
              // off dead against the divider.
              const SizedBox(
                width: double.infinity,
                height: 20,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [Colors.transparent, _navSurface],
                    ),
                  ),
                ),
              ),
              Container(
                width: double.infinity,
                height: 80,
                padding: const EdgeInsets.symmetric(horizontal: 20),
                decoration: const BoxDecoration(
                  color: _navSurface,
                  border: Border(top: BorderSide(color: _navDivider, width: 0.5)),
                ),
                child: Row(
                  children: [
                    _buildTab(context, home, 0, FontAwesomeIcons.house, 'Home', context.l10n.navHome),
                    _buildTab(context, home, 1, FontAwesomeIcons.comments, 'Conversations', context.l10n.navConvos),
                    _buildTab(context, home, 2, FontAwesomeIcons.brain, 'Brain', context.l10n.navBrain),
                    _buildTab(context, home, 3, FontAwesomeIcons.listCheck, 'Tasks', context.l10n.navTodos),
                    _buildTab(context, home, 4, FontAwesomeIcons.tableCellsLarge, 'Apps', context.l10n.apps),
                  ],
                ),
              ),
            ],
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
