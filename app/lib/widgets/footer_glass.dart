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
    // wrap() is called for its side effect only: with no theme and no adaptive quality it just
    // registers the brightness resolver, and the widget it returns is not needed. That holds for
    // the pinned 1.21.0; check it again when the pin moves.
    LiquidGlassWidgets.wrap(child: const SizedBox.shrink(), brightnessResolver: Theme.maybeBrightnessOf);
    // The package's monitor raises a FlutterError in debug and profile builds when frames run over
    // its budget; the app has its own frame telemetry. A failed preload is not fatal either: the
    // glass then compiles its shaders on first use.
    unawaited(LiquidGlassWidgets.initialize(enablePerformanceMonitor: false).catchError((Object _) {}));
  }

  /// The package's copy of the iOS regular material, with more frost than the preset. At the
  /// preset's own opacity (0.85 dark, 0.73 light) a line of text passing behind a control stays
  /// readable and collides with the control's label; at 1 nothing of the content shows through.
  static LiquidGlassSettings settingsFor(Brightness brightness) =>
      (brightness == Brightness.dark ? LiquidGlassSettings.ios27Dark : LiquidGlassSettings.ios27Light)
          .copyWith(frostOpacity: 1);
}

/// The glass body of one footer control: a pill as wide as its parent allows, or a circle of
/// [height].
///
/// With [onTap] it is a glass button: it answers a press the way iOS glass does (it swells on a
/// spring, lights up under the finger and stretches a little when dragged) and calls [onTap].
/// Semantics stay with the caller. Without [onTap] it is paint only, for a bar that holds its own
/// buttons.
class FooterGlassSurface extends StatelessWidget {
  const FooterGlassSurface({
    super.key,
    required this.height,
    required this.child,
    this.circle = false,
    this.padding,
    this.onTap,
  });

  final double height;
  final Widget child;
  final bool circle;
  final EdgeInsetsGeometry? padding;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final shape = circle ? const LiquidOval() : LiquidRoundedSuperellipse(borderRadius: height / 2);
    final settings = FooterGlass.settingsFor(Theme.of(context).brightness);
    // Own layer: the footers are not inside a glass page. Premium is the mode that shows what is
    // behind the surface; the package falls back by itself where the renderer cannot do it.
    final Widget glass = onTap == null
        ? GlassContainer(
            width: circle ? height : null,
            height: height,
            alignment: Alignment.center,
            padding: padding,
            shape: shape,
            useOwnLayer: true,
            quality: GlassQuality.premium,
            settings: settings,
            child: child,
          )
        : GlassButton.custom(
            onTap: onTap!,
            width: circle ? height : double.infinity,
            height: height,
            shape: shape,
            useOwnLayer: true,
            quality: GlassQuality.premium,
            settings: settings,
            // The caller's Semantics node carries the label and the actions.
            excludeFromSemantics: true,
            child: padding == null ? child : Padding(padding: padding!, child: child),
          );
    // Own repaint boundary: the page around a footer repaints on every scroll frame, and the
    // control should not be repainted with it.
    return RepaintBoundary(child: glass);
  }
}
