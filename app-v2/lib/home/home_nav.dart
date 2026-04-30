/// Lightweight navigation handle exposed to Home stream cards via Provider.
/// Cards call `switchToTab(...)` instead of holding a callback field, which
/// keeps them serializable to Hive without losing nav capability.
class HomeNav {
  HomeNav({required this.switchToTab});

  /// Index of the Plan tab in `ShellScreen` — pinned here so cards don't
  /// hardcode a magic number.
  static const int planTabIndex = 3;

  final void Function(int tabIndex) switchToTab;
}
