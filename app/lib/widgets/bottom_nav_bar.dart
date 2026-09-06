import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/home_provider.dart';

class BottomNavBar extends StatefulWidget {
  const BottomNavBar({super.key, required this.onTabTap, this.onTabWarmup});

  final void Function(int index, bool isRepeat) onTabTap;
  final ValueChanged<int>? onTabWarmup;

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
        // The app targets SDK 36, so Android 15+ enforces edge-to-edge and this
        // Stack extends under the system navigation bar. Reserve the bottom
        // inset so the tab row stays above it; without this the row's tap
        // targets sit behind the 3-button navigation bar. The sibling bars
        // mounted in the same home Stack (MergeActionBar, TaskSelectionActionBar)
        // already use SafeArea for the same reason.
        //
        // viewPadding, not padding: the home Scaffold sets
        // resizeToAvoidBottomInset: false, and padding.bottom collapses to zero
        // while a keyboard is open, which would drop the row back under the bar.
        final bottomInset = MediaQuery.viewPaddingOf(context).bottom;
        return Align(
          alignment: Alignment.bottomCenter,
          child: Container(
            width: double.infinity,
            // The 80dp content box is unchanged; only the reserved inset grows,
            // so a device reporting a zero inset lays out exactly as before.
            height: 100 + bottomInset,
            padding: EdgeInsets.fromLTRB(20, 20, 20, bottomInset),
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
        onTapDown: (_) => widget.onTabWarmup?.call(index),
        onTap: () {
          // Switch the visible page before crossing the platform channel for
          // haptics or analytics. Both can be delayed when the device is busy,
          // but neither should delay visual acknowledgement of the tap.
          widget.onTabTap(index, context.read<HomeProvider>().selectedIndex == index);
          primaryFocus?.unfocus();
          WidgetsBinding.instance.addPostFrameCallback((_) {
            HapticFeedback.selectionClick();
            PlatformManager.instance.analytics.bottomNavigationTabClicked(label);
          });
        },
        child: SizedBox(
          height: 90,
          child: Center(child: FaIcon(icon, color: selectedIndex == index ? Colors.white : Colors.grey, size: 26)),
        ),
      ),
    );
  }
}
