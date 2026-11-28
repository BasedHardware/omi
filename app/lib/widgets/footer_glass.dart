import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';

/// The body of one footer control in the experimental design
/// (`lib/services/experiments/experimental_design.dart`): a frosted pill as wide as its parent
/// allows, or a circle of [height], with a light rim and a soft shadow.
///
/// It answers a touch like glass: while a finger is on it, it swells by [GlassStyle.pressScale] and
/// lightens, whether the tap is its own ([onTap]) or belongs to a button inside it. [swell] false
/// leaves it still, for a wide bar that holds several controls. Semantics stay with the caller.
/// The experimental design's rules for a raised control, by its height, so the footer's buttons,
/// the top bar's and the smaller chips are one family:
/// - shadow: blur is half the control's height and it falls a ninth of the height below, so a
///   36 pt chip throws a tighter shadow than a 56 pt button; `raised` (over a page of text) is
///   darker and falls further;
/// - press: a control grows by about 4 pt of its height while a finger is on it, so a small control
///   grows by a larger share than a large one (56 pt: 6 %, 40 pt: 9 %, 34 pt: 10 %), never more than 12 %;
/// - a button inside a shared capsule grows on its own ([GlassPressItem]); the capsule stays still.
abstract final class GlassStyle {
  static const Duration pressIn = Duration(milliseconds: 160);

  /// The fill, the lighter fill under a finger, and the rim.
  static Color fill(bool dark) => dark ? const Color(0xE02C2C2E) : const Color(0xE6FFFFFF);
  static Color pressedFill(bool dark) => dark ? const Color(0xF03A3A3C) : const Color(0xFFFFFFFF);
  static Color rim(bool dark) => dark ? const Color(0x24FFFFFF) : const Color(0xFFFFFFFF);

  static BoxShadow shadow(double height, {required bool dark, bool raised = false}) => raised
      ? BoxShadow(
          color: Color(dark ? 0x80000000 : 0x2E000000),
          blurRadius: height * 0.57,
          offset: Offset(0, height * 0.18),
        )
      : BoxShadow(
          color: Color(dark ? 0x59000000 : 0x1A000000),
          blurRadius: height * 0.5,
          offset: Offset(0, height * 0.11),
        );

  static double pressScale(double height) => (1 + 3.5 / height).clamp(1.0, 1.12);

  /// A button inside a shared capsule: the glyph and the bubble that appears around it.
  static const double itemPressScale = 1.22;
}

class FooterGlassSurface extends StatelessWidget {
  const FooterGlassSurface({
    super.key,
    required this.height,
    required this.child,
    this.circle = false,
    this.padding,
    this.onTap,
    this.raised = false,
    this.swell = true,
  });

  /// A stronger shadow, for a control over a page of text.
  final bool raised;

  /// Whether a touch makes it swell.
  final bool swell;

  final double height;
  final Widget child;
  final bool circle;
  final EdgeInsetsGeometry? padding;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return _FooterBlurSurface(
        height: height, circle: circle, raised: raised, swell: swell, padding: padding, onTap: onTap, child: child);
  }
}

/// The content behind is blurred by Flutter's own backdrop filter, then tinted. Controls under one [BackdropGroup] share a single read of the backdrop.
class _FooterBlurSurface extends StatefulWidget {
  const _FooterBlurSurface({
    required this.height,
    required this.child,
    required this.circle,
    required this.raised,
    required this.swell,
    this.padding,
    this.onTap,
  });

  final bool raised;
  final bool swell;

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
    if (widget.swell && _down != down && mounted) setState(() => _down = down);
  }

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final radius = BorderRadius.circular(widget.height / 2);
    // A flat fill a little lighter than the page and nearly opaque: what is behind shows as a
    // faint shape only. The edge is a highlight, lighter than the fill, never a dark line; the
    // control separates from the page by its shadow.
    final fill = GlassStyle.fill(dark);
    final pressed = GlassStyle.pressedFill(dark);
    final rim = GlassStyle.rim(dark);
    final shadow = GlassStyle.shadow(widget.height, dark: dark, raised: widget.raised);
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
        // omi-perf-allow: blur-filter -- the experimental design's raised controls, behind its switch (default off); grouped so one page's controls share one backdrop read; measured on an iPhone 16 Pro at 1.2-1.8 ms raster per frame against 0.9 ms flat
        child: BackdropFilter.grouped(filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20), child: body),
      ),
    );
    // A Listener, not a gesture: a button inside the surface keeps its own tap.
    final pressable = Listener(
      onPointerDown: (_) => _set(true),
      onPointerUp: (_) => _set(false),
      onPointerCancel: (_) => _set(false),
      child: AnimatedScale(
        scale: _down ? GlassStyle.pressScale(widget.height) : 1,
        duration: GlassStyle.pressIn,
        curve: Curves.easeOut,
        child: surface,
      ),
    );
    if (widget.onTap == null) return pressable;
    return GestureDetector(behavior: HitTestBehavior.opaque, onTap: widget.onTap, child: pressable);
  }
}

/// The same press growth for a control that is not a frosted surface (the flat red End, a tab
/// capsule). [height] is the control's, which sets how far it grows ([GlassStyle.pressScale]).
class PressSwell extends StatefulWidget {
  const PressSwell({super.key, required this.height, required this.child});

  final double height;
  final Widget child;

  @override
  State<PressSwell> createState() => _PressSwellState();
}

class _PressSwellState extends State<PressSwell> {
  bool _down = false;

  void _set(bool down) {
    if (_down != down && mounted) setState(() => _down = down);
  }

  @override
  Widget build(BuildContext context) {
    return Listener(
      onPointerDown: (_) => _set(true),
      onPointerUp: (_) => _set(false),
      onPointerCancel: (_) => _set(false),
      child: AnimatedScale(
        scale: _down ? GlassStyle.pressScale(widget.height) : 1,
        duration: GlassStyle.pressIn,
        curve: Curves.easeOut,
        child: widget.child,
      ),
    );
  }
}

/// One button inside a capsule that several share: under a finger it alone grows, on a lighter
/// bubble with its own shadow that rises out of the capsule, as a glass toolbar's item does. The
/// capsule does not move.
class GlassPressItem extends StatefulWidget {
  const GlassPressItem({super.key, required this.child, this.diameter = 36});

  final Widget child;

  /// The bubble's size at rest.
  final double diameter;

  @override
  State<GlassPressItem> createState() => _GlassPressItemState();
}

class _GlassPressItemState extends State<GlassPressItem> {
  bool _down = false;

  void _set(bool down) {
    if (_down != down && mounted) setState(() => _down = down);
  }

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    return Listener(
      onPointerDown: (_) => _set(true),
      onPointerUp: (_) => _set(false),
      onPointerCancel: (_) => _set(false),
      child: AnimatedScale(
        scale: _down ? GlassStyle.itemPressScale : 1,
        duration: GlassStyle.pressIn,
        curve: Curves.easeOut,
        child: Stack(
          alignment: Alignment.center,
          children: [
            Positioned.fill(
              child: IgnorePointer(
                child: Center(
                  child: AnimatedOpacity(
                    opacity: _down ? 1 : 0,
                    duration: const Duration(milliseconds: 120),
                    child: Container(
                      width: widget.diameter,
                      height: widget.diameter,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: GlassStyle.pressedFill(dark),
                        border: Border.all(color: GlassStyle.rim(dark)),
                        boxShadow: [GlassStyle.shadow(widget.diameter, dark: dark, raised: true)],
                      ),
                    ),
                  ),
                ),
              ),
            ),
            widget.child,
          ],
        ),
      ),
    );
  }
}
