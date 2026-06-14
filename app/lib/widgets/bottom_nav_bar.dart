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
                _buildTab(context, home, 0, FontAwesomeIcons.eye, context.l10n.objectAnnouncementsDetectTab),
                _buildTab(context, home, 1, FontAwesomeIcons.gear, context.l10n.settings),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildTab(BuildContext context, HomeProvider home, int index, FaIconData icon, String label) {
    return Expanded(
      child: InkWell(
        onTap: () {
          HapticFeedback.mediumImpact();
          PlatformManager.instance.analytics.bottomNavigationTabClicked(label);
          primaryFocus?.unfocus();
          onTabTap(index, home.selectedIndex == index);
        },
        child: SizedBox(
          height: 90,
          child: Center(child: FaIcon(icon, color: home.selectedIndex == index ? Colors.white : Colors.grey, size: 26)),
        ),
      ),
    );
  }
}
