import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';

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
  });

  /// A stronger shadow, for a control over a page of text.
  final bool raised;

  final double height;
  final Widget child;
  final bool circle;
  final EdgeInsetsGeometry? padding;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) =>
      _FooterBlurSurface(height: height, circle: circle, raised: raised, padding: padding, onTap: onTap, child: child);
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
