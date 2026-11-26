import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

/// Glass footers on iPhone. The floating controls at the bottom of Home (Ask anything, record, the
/// recording bar) and of the conversation page (Ask Omi, the audio player, End Conversation) are
/// drawn as glass that shows the content scrolling behind them, and the page-coloured backdrop
/// those screens paint under the row is left out so there is something behind the glass.
///
/// iOS only: every other platform builds exactly what it built before. A build made with
/// `--dart-define=OMI_FOOTER_GLASS_OFF=true` keeps the flat footers on iOS as well.
class FooterGlass {
  FooterGlass._();

  static const bool _off = bool.fromEnvironment('OMI_FOOTER_GLASS_OFF');

  /// Tests set this to exercise either look on the host.
  @visibleForTesting
  static bool? debugOverride;

  static bool get enabled => debugOverride ?? (!_off && defaultTargetPlatform == TargetPlatform.iOS);

  /// Called once at startup. Loads the glass shaders in the background and tells the package to
  /// follow the app's own light/dark choice rather than the system's. Does nothing when off.
  static void setUp() {
    if (!enabled) return;
    // wrap() only registers the resolver here; the returned widget is not used.
    LiquidGlassWidgets.wrap(child: const SizedBox.shrink(), brightnessResolver: Theme.maybeBrightnessOf);
    unawaited(LiquidGlassWidgets.initialize());
  }

  /// The package's copy of the iOS regular material, with the frost fully covering what is behind.
  /// At the preset's own opacity (0.85 dark, 0.73 light) a line of text passing behind a control
  /// stays readable and collides with the control's label; at 1 it becomes a soft colour cloud.
  static LiquidGlassSettings settingsFor(Brightness brightness) =>
      (brightness == Brightness.dark ? LiquidGlassSettings.ios27Dark : LiquidGlassSettings.ios27Light)
          .copyWith(frostOpacity: 1);
}

/// The glass body of one footer control: a pill as wide as its parent allows, or a circle of
/// [height]. Paint only; gestures and semantics stay with the caller.
class FooterGlassSurface extends StatelessWidget {
  const FooterGlassSurface({
    super.key,
    required this.height,
    required this.child,
    this.circle = false,
    this.padding,
  });

  final double height;
  final Widget child;
  final bool circle;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    return GlassContainer(
      width: circle ? height : null,
      height: height,
      alignment: Alignment.center,
      padding: padding,
      shape: circle ? const LiquidOval() : LiquidRoundedSuperellipse(borderRadius: height / 2),
      // Own layer: the footers are not inside a glass page. Premium is the mode that shows what is
      // behind the surface; the package falls back by itself where the renderer cannot do it.
      useOwnLayer: true,
      quality: GlassQuality.premium,
      settings: FooterGlass.settingsFor(Theme.of(context).brightness),
      child: child,
    );
  }
}
