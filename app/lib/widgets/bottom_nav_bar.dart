import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The bar's opaque fill — a near-black just off the page's true black, so the
/// bar separates from the content without becoming a bright band.
const Color _navSurface = Color.fromARGB(255, 15, 15, 15);

/// Hairline separating the bar from the page. 0.5 logical px renders as a true
/// hairline on 2x/3x screens. White at low alpha against the bar's near-black
/// surface — a black hairline would be invisible on it.
const Color _navDivider = Color(0x14FFFFFF);

/// Selected tab. White against the bar's near-black surface.
const Color _navSelected = Color(0xFFFFFFFF);

/// Unselected tab. Enough contrast on the dark surface to stay legible without
/// competing with the selected one.
const Color _navUnselected = Color(0xFF8A8A8E);

class BottomNavBar extends StatelessWidget {
  const BottomNavBar({super.key, required this.onTabTap});

  final void Function(int index, bool isRepeat) onTabTap;

  @override
  Widget build(BuildContext context) {
    return Consumer<HomeProvider>(
      builder: (context, home, child) {
        return Align(
          alignment: Alignment.bottomCenter,
          // One solid 80pt bar with a hairline on top. The clearances that keep
          // the chat composer and the Brain graph off the bar are measured
          // against that 80.
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // No scrim strip above the bar. A fade from transparent to the
              // page colour reads as haze over dark content rather than as a
              // soft edge; the hairline below is a cleaner boundary.
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
                    _buildTab(context, home, 0, FontAwesomeIcons.comments, 'Conversations', context.l10n.navConvos),
                    // Analytics label stays 'Home': it is the same destination
                    // this event has always counted, only renamed and moved.
                    _buildTab(context, home, 1, FontAwesomeIcons.commentDots, 'Home', context.l10n.chat),
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
    final color = isSelected ? _navSelected : _navUnselected;
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
