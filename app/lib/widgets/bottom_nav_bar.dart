import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Height of the gradient that fades page content out above the tab row. It is
/// paint only: nothing in it is tappable.
const double kBottomNavFadeHeight = 20;

/// Height of the tab row, which sits directly on top of the system inset the
/// way a platform tab bar does (UITabBar's content row is 49pt, Material's
/// bottom navigation 56dp; both then add the system inset underneath). The row
/// carries no slack of its own below the icons: the inset is the only space
/// between the row and the screen edge, so a device reporting a large inset
/// does not end up with two stacked gaps.
const double kBottomNavRowHeight = 52;

/// Height of the bottom nav above whatever system inset it reserves.
const double kBottomNavBarHeight = kBottomNavFadeHeight + kBottomNavRowHeight;

/// Gap between the top of the tab row and the home chat bar that floats above
/// it. The chat bar derives its offset from the row's geometry rather than
/// repeating a literal, so changing the row's height cannot silently close it.
const double kBottomNavChatBarGap = 4;

/// The bottom inset the nav row reserves for system chrome. Anything
/// positioned against the row must add this to stay in step with it.
///
/// viewPadding, not padding: the home Scaffold sets
/// resizeToAvoidBottomInset: false, and padding.bottom collapses to zero while
/// a keyboard is open, which would drop the row back under the system bar.
double bottomNavBarReservedInset(BuildContext context) => MediaQuery.viewPaddingOf(context).bottom;

/// Distance from the bottom of the screen to the top of the nav bar. Content
/// that scrolls or floats behind the bar in the home shell clears this rather
/// than a literal, so it follows both the row's height and the device's inset.
double bottomNavBarClearance(BuildContext context) => kBottomNavBarHeight + bottomNavBarReservedInset(context);

/// Height of the home chat bar that floats above the tab row.
const double kHomeChatBarHeight = 62;

/// Offset from the bottom of the screen to the bottom edge of the home chat bar.
double bottomNavChatBarOffset(BuildContext context) =>
    kBottomNavRowHeight + kBottomNavChatBarGap + bottomNavBarReservedInset(context);

/// Distance from the bottom of the screen that home-tab content must clear to
/// stay out from under the floating chat bar, with a little air above it.
double homeChatBarClearance(BuildContext context) => bottomNavChatBarOffset(context) + kHomeChatBarHeight + 20;

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
        // Reserve whatever bottom inset the window reports so the tab row's tap
        // targets stay above the system navigation bar. When the window is not
        // drawn under that bar the reported inset is zero and this is a no-op,
        // so the row can never be lifted twice. The sibling bars mounted in the
        // same home Stack (MergeActionBar, TaskSelectionActionBar) already use
        // SafeArea to reserve the same inset.
        final bottomInset = bottomNavBarReservedInset(context);
        final height = kBottomNavBarHeight + bottomInset;
        return Align(
          alignment: Alignment.bottomCenter,
          child: Container(
            width: double.infinity,
            // The content box is fixed; only the reserved inset grows.
            height: height,
            padding: EdgeInsets.fromLTRB(20, kBottomNavFadeHeight, 20, bottomInset),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                // The fade ends where the tab row begins whatever the inset is,
                // so the row and the inset below it are always solid.
                stops: [0.0, kBottomNavFadeHeight / height, 1.0],
                colors: const [Colors.transparent, Color.fromARGB(255, 15, 15, 15), Color.fromARGB(255, 15, 15, 15)],
              ),
            ),
            child: Row(
              children: [
                _buildTab(context, selectedIndex, 0, FontAwesomeIcons.house, 'Home', context.l10n.home),
                _buildTab(
                    context, selectedIndex, 1, FontAwesomeIcons.comments, 'Conversations', context.l10n.conversations),
                _buildTab(context, selectedIndex, 2, FontAwesomeIcons.listCheck, 'Tasks', context.l10n.tasks),
                _buildTab(context, selectedIndex, 3, FontAwesomeIcons.puzzlePiece, 'Apps', context.l10n.apps),
              ],
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) => _navigation;

  /// [label] is the stable analytics name; [semanticLabel] is what a screen
  /// reader announces, since the tabs are icon-only.
  Widget _buildTab(
    BuildContext context,
    int selectedIndex,
    int index,
    FaIconData icon,
    String label,
    String semanticLabel,
  ) {
    return Expanded(
      child: Semantics(
        button: true,
        selected: selectedIndex == index,
        label: semanticLabel,
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
            height: kBottomNavRowHeight,
            child: Center(child: FaIcon(icon, color: selectedIndex == index ? Colors.white : Colors.grey, size: 26)),
          ),
        ),
      ),
    );
  }
}
