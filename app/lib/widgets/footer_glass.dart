import 'dart:async';
import 'dart:io' show Platform;
import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';

import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

/// How a footer control is drawn in the experimental design.
enum FooterGlassStyle {
  /// Flutter's own backdrop blur under a white tint, a light rim and a soft shadow.
  blur,

  /// The glass package's material at 92% frost: bends and frosts what is behind it, and answers a
  /// press the way iOS glass does. Costs about twice the frame time of [blur].
  glass,
}

/// The glass package, set up the first time a [FooterGlassStyle.glass] surface is built, so an
/// app that never shows one loads none of it.
abstract final class FooterGlass {
  static bool _ready = false;

  static void ensureSetUp() {
    if (_ready) return;
    _ready = true;
    // wrap() is called for its side effect only: with no theme and no adaptive quality it just
    // registers the brightness resolver (the app's own light/dark choice, not the system's), and
    // the widget it returns is not needed. That holds for the pinned 1.21.0.
    LiquidGlassWidgets.wrap(child: const SizedBox.shrink(), brightnessResolver: Theme.maybeBrightnessOf);
    // The package's monitor raises a FlutterError when frames run over its budget; the app has its
    // own frame telemetry. A failed preload is not fatal: the glass compiles its shaders on first use.
    // Not under `flutter test`, which has no shader assets to preload.
    if (Platform.environment.containsKey('FLUTTER_TEST')) return;
    unawaited(LiquidGlassWidgets.initialize(enablePerformanceMonitor: false).catchError((Object _) {}));
  }

  /// The package's copy of the iOS regular material with more frost than the preset: at 0.92 a
  /// line of text behind a control shows as a soft shape only.
  static LiquidGlassSettings settingsFor(Brightness brightness) =>
      (brightness == Brightness.dark ? LiquidGlassSettings.ios27Dark : LiquidGlassSettings.ios27Light)
          .copyWith(frostOpacity: 0.92);
}

/// The body of one footer control in the experimental design
/// (`lib/services/experiments/experimental_design.dart`): a frosted pill as wide as its parent
/// allows, or a circle of [height], with a light rim and a soft shadow.
///
/// With [onTap] it answers a press (it swells a little and lightens) and calls [onTap]. Semantics
/// stay with the caller. Without [onTap] it is paint only, for a bar that holds its own buttons.
class FooterGlassSurface extends StatelessWidget {
  const FooterGlassSurface({
    super.key,
    required this.height,
    required this.child,
    this.circle = false,
    this.padding,
    this.onTap,
    this.raised = false,
    this.style = FooterGlassStyle.blur,
  });

  final FooterGlassStyle style;

  /// A stronger shadow, for a control over a page of text.
  final bool raised;

  final double height;
  final Widget child;
  final bool circle;
  final EdgeInsetsGeometry? padding;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    if (style == FooterGlassStyle.blur) {
      return _FooterBlurSurface(
          height: height, circle: circle, raised: raised, padding: padding, onTap: onTap, child: child);
    }
    FooterGlass.ensureSetUp();
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
    return RepaintBoundary(child: glass);
  }
}

/// The content behind is blurred by Flutter's own backdrop filter, then tinted. Controls under one [BackdropGroup] share a single read of the backdrop.
class _FooterBlurSurface extends StatefulWidget {
  const _FooterBlurSurface({
    required this.height,
    required this.child,
    required this.circle,
    required this.raised,
    this.padding,
    this.onTap,
  });

  final bool raised;

  final double height;
  final Widget child;
  final bool circle;
  final EdgeInsetsGeometry? padding;
  final VoidCallback? onTap;

  @override
  State<_FooterBlurSurface> createState() => _FooterBlurSurfaceState();
}

class _FooterBlurSurfaceState extends State<_FooterBlurSurface> {
  bool _down = false;

  void _set(bool down) {
    if (widget.onTap != null && _down != down) setState(() => _down = down);
  }

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final radius = BorderRadius.circular(widget.height / 2);
    // A flat fill a little lighter than the page and nearly opaque: what is behind shows as a
    // faint shape only. The edge is a highlight, lighter than the fill, never a dark line; the
    // control separates from the page by its shadow.
    final fill = dark ? const Color(0xE02C2C2E) : const Color(0xE6FFFFFF);
    final pressed = dark ? const Color(0xF03A3A3C) : const Color(0xFFFFFFFF);
    final rim = dark ? const Color(0x24FFFFFF) : const Color(0xFFFFFFFF);
    final shadow = widget.raised
        ? BoxShadow(color: Color(dark ? 0x80000000 : 0x2E000000), blurRadius: 32, offset: const Offset(0, 10))
        : BoxShadow(color: Color(dark ? 0x59000000 : 0x1A000000), blurRadius: 28, offset: const Offset(0, 6));
    final body = AnimatedContainer(
      duration: const Duration(milliseconds: 120),
      width: widget.circle ? widget.height : null,
      height: widget.height,
      alignment: Alignment.center,
      padding: widget.padding,
      decoration: BoxDecoration(
        color: _down ? pressed : fill,
        borderRadius: radius,
        border: Border.all(color: rim, width: 1),
      ),
      child: widget.child,
    );
    final surface = DecoratedBox(
      decoration: BoxDecoration(borderRadius: radius, boxShadow: [shadow]),
      child: ClipRRect(
        borderRadius: radius,
        child: BackdropFilter.grouped(filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20), child: body),
      ),
    );
    if (widget.onTap == null) return surface;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: widget.onTap,
      onTapDown: (_) => _set(true),
      onTapUp: (_) => _set(false),
      onTapCancel: () => _set(false),
      child: AnimatedScale(
        scale: _down ? 1.04 : 1,
        duration: const Duration(milliseconds: 160),
        curve: Curves.easeOut,
        child: surface,
      ),
    );
  }
}
