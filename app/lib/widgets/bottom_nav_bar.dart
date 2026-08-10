import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/home_provider.dart';

class BottomNavBar extends StatefulWidget {
  const BottomNavBar({super.key, required this.onTabTap});

  final void Function(int index, bool isRepeat) onTabTap;

  @override
  State<BottomNavBar> createState() => _BottomNavBarState();
}

class _BottomNavBarState extends State<BottomNavBar> {
  // Keep the provider-dependent subtree stable when HomePage's broad Consumer
  // rebuilds for unrelated focus or loading changes.
  late final Widget _navigation;

  @override
  void initState() {
    super.initState();
    _navigation = Selector<HomeProvider, int>(
      selector: (_, home) => home.selectedIndex,
      builder: (context, selectedIndex, _) {
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
                _buildTab(context, selectedIndex, 0, FontAwesomeIcons.house, 'Home'),
                _buildTab(context, selectedIndex, 1, FontAwesomeIcons.comments, 'Conversations'),
                _buildTab(context, selectedIndex, 2, FontAwesomeIcons.listCheck, 'Tasks'),
                _buildTab(context, selectedIndex, 3, FontAwesomeIcons.puzzlePiece, 'Apps'),
              ],
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) => _navigation;

  Widget _buildTab(BuildContext context, int selectedIndex, int index, FaIconData icon, String label) {
    return Expanded(
      child: InkWell(
        onTap: () {
          HapticFeedback.mediumImpact();
          PlatformManager.instance.analytics.bottomNavigationTabClicked(label);
          primaryFocus?.unfocus();
          widget.onTabTap(index, context.read<HomeProvider>().selectedIndex == index);
        },
        child: SizedBox(
          height: 90,
          child: Center(child: FaIcon(icon, color: selectedIndex == index ? Colors.white : Colors.grey, size: 26)),
        ),
      ),
    );
  }
}
