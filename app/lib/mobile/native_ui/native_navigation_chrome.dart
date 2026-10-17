import 'package:flutter/widgets.dart';

import 'ios_native_surface.dart';

/// The current navigation owner supplies chrome; the child remains the only native screen.
/// A child that cannot project all controls restores the complete original navigation too.
class NativeNavigationChrome extends InheritedWidget {
  const NativeNavigationChrome(
      {super.key,
      required super.child,
      this.sections = const [],
      this.toolbar = const [],
      this.wrapFallback,
      this.enabled = true});
  final List<NativeSection> sections;
  final List<NativeRow> toolbar;
  final Widget Function(Widget)? wrapFallback;
  final bool enabled;

  static NativeNavigationChrome? of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<NativeNavigationChrome>();
    return scope?.enabled == true ? scope : null;
  }

  @override
  bool updateShouldNotify(NativeNavigationChrome oldWidget) => true;
}
