import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import 'package:omi/ui/omi_tokens.dart';

/// Which palette the app wears: the phone's own setting, or always light, or always dark.
enum OmiAppearanceMode { system, light, dark }

/// The app's appearance choice (Settings → Appearance). [OmiAppearanceScope] follows it; the app
/// restores the saved choice at launch and saves each change.
abstract final class OmiAppearance {
  static final ValueNotifier<OmiAppearanceMode> mode = ValueNotifier(OmiAppearanceMode.system);

  /// The palette for [mode] when the phone itself is in [platform] brightness.
  static OmiPalette resolve(OmiAppearanceMode mode, Brightness platform) {
    return switch (mode) {
      OmiAppearanceMode.light => OmiPalette.light,
      OmiAppearanceMode.dark => OmiPalette.dark,
      OmiAppearanceMode.system => platform == Brightness.light ? OmiPalette.light : OmiPalette.dark,
    };
  }

  /// The status bar and home indicator that read on [palette]'s page.
  static SystemUiOverlayStyle overlayFor(OmiPalette palette) =>
      palette.isLight ? SystemUiOverlayStyle.dark : SystemUiOverlayStyle.light;
}

/// Puts the chosen palette into effect above the app: switches [OmiColors] (and with it every
/// [OmiType] style) and rebuilds everything below, keeping each screen's state, whenever the
/// choice or the phone's own appearance changes.
class OmiAppearanceScope extends StatefulWidget {
  const OmiAppearanceScope({super.key, required this.builder});

  /// Builds the app. Runs again after every palette switch, so a theme built here is current.
  final WidgetBuilder builder;

  @override
  State<OmiAppearanceScope> createState() => _OmiAppearanceScopeState();
}

class _OmiAppearanceScopeState extends State<OmiAppearanceScope> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    OmiAppearance.mode.addListener(_apply);
    _apply(initial: true);
  }

  @override
  void dispose() {
    OmiAppearance.mode.removeListener(_apply);
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangePlatformBrightness() => _apply();

  void _apply({bool initial = false}) {
    final platform = WidgetsBinding.instance.platformDispatcher.platformBrightness;
    final palette = OmiAppearance.resolve(OmiAppearance.mode.value, platform);
    final changed = !identical(palette, OmiColors.palette);
    OmiColors.use(palette);
    SystemChrome.setSystemUIOverlayStyle(OmiAppearance.overlayFor(palette));
    if (initial || !changed || !mounted) return;
    setState(() {});
    // Colours are read straight from [OmiColors] in build methods, not through an inherited
    // widget, so nothing below would notice the switch on its own: mark every element for rebuild.
    // State is kept; only build methods run again.
    void mark(Element element) {
      element.markNeedsBuild();
      element.visitChildren(mark);
    }

    (context as Element).visitChildren(mark);
  }

  @override
  Widget build(BuildContext context) => widget.builder(context);
}
