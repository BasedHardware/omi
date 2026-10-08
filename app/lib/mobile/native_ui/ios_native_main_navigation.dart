import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

import 'ios_native_surface.dart';

const nativeMainDestinations = ['home', 'tasks', 'memories', 'apps', 'settings'];

/// The system tab bar the shell reserves above the home indicator.
const nativeTabBarReserve = 64.0;

/// NativeHomeView's footer controls: 44 pt glass buttons with 10 pt of vertical padding on each side.
const nativeHomeFooterHeight = 64.0;

/// Presentation-only root navigation. Providers and pushed routes remain with
/// their existing owners; a page mounts once, when first visited.
class IosNativeMainShell extends StatefulWidget {
  const IosNativeMainShell({
    super.key,
    required this.pages,
    required this.homeIndex,
    required this.navigationRevision,
    required this.onHomeTabSelected,
    this.onHomeReselected,
  });

  final Map<String, WidgetBuilder> pages;
  final int homeIndex, navigationRevision;
  final ValueChanged<int> onHomeTabSelected;
  final VoidCallback? onHomeReselected;

  @override
  State<IosNativeMainShell> createState() => _IosNativeMainShellState();
}

class _IosNativeMainShellState extends State<IosNativeMainShell> {
  late String _selected = widget.homeIndex == 1 ? 'tasks' : 'home';
  late final Set<String> _visited = {'home', _selected};
  double Function(BuildContext context)? _previousClearance;

  @override
  void initState() {
    super.initState();
    // Toasts float above the tab bar, and above Home's footer on Home, while this shell is the visible route.
    _previousClearance = OmiFeedback.bottomClearance;
    OmiFeedback.bottomClearance = _feedbackClearance;
  }

  double _feedbackClearance(BuildContext context) =>
      nativeTabBarReserve + (_selected == 'home' ? nativeHomeFooterHeight : 0);

  @override
  void didUpdateWidget(IosNativeMainShell oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.navigationRevision != oldWidget.navigationRevision) {
      _selected = widget.homeIndex == 1 ? 'tasks' : 'home';
      _visited.add(_selected);
    }
  }

  void _select(String id) {
    if (!mounted || !nativeMainDestinations.contains(id)) return;
    if (id == _selected) {
      if (id == 'home') widget.onHomeReselected?.call();
      return;
    }
    OmiHaptics.selection();
    setState(() {
      _selected = id;
      _visited.add(id);
    });
    if (id == 'home' || id == 'tasks') widget.onHomeTabSelected(id == 'home' ? 0 : 1);
  }

  @override
  Widget build(BuildContext context) {
    final labels = <String, String>{
      'home': context.l10n.home,
      'tasks': context.l10n.tasks,
      'memories': context.l10n.memories,
      'apps': context.l10n.apps,
      'settings': context.l10n.settings,
    };
    final navigation = NativeRow('main_destination', '',
        kind: 'segmented', value: _selected, options: labels, action: (value) => _select(value as String));
    // Reserve the entire system tab bar and home indicator. The screen and its
    // pinned controls stay above it, rather than being covered by an overlay.
    final bottom = MediaQuery.viewPaddingOf(context).bottom;
    return Column(children: [
      Expanded(
        child: MediaQuery.removePadding(
          context: context,
          removeBottom: true,
          child: IndexedStack(
            key: const Key('native_main_pages'),
            index: nativeMainDestinations.indexOf(_selected),
            children: [
              for (final id in nativeMainDestinations)
                KeyedSubtree(
                  key: ValueKey('native_main_page_$id'),
                  child: _visited.contains(id) ? Builder(builder: widget.pages[id]!) : const SizedBox.shrink(),
                ),
            ],
          ),
        ),
      ),
      SizedBox(
        key: const Key('native_main_navigation'),
        height: nativeTabBarReserve + bottom,
        child: IosNativeSurface(
          title: '',
          sections: const [],
          navigation: navigation,
          fallback: NavigationBar(
            selectedIndex: nativeMainDestinations.indexOf(_selected),
            onDestinationSelected: (index) => _select(nativeMainDestinations[index]),
            destinations: [
              NavigationDestination(icon: const Icon(Icons.home_outlined), label: labels['home']!),
              NavigationDestination(icon: const Icon(Icons.checklist), label: labels['tasks']!),
              NavigationDestination(icon: const Icon(Icons.psychology_outlined), label: labels['memories']!),
              NavigationDestination(icon: const Icon(Icons.apps), label: labels['apps']!),
              NavigationDestination(icon: const Icon(Icons.settings_outlined), label: labels['settings']!),
            ],
          ),
        ),
      ),
    ]);
  }

  @override
  void dispose() {
    if (OmiFeedback.bottomClearance == _feedbackClearance) OmiFeedback.bottomClearance = _previousClearance;
    super.dispose();
  }
}
