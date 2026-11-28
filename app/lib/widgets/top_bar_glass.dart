import 'package:flutter/material.dart';

import 'package:omi/widgets/footer_glass.dart';

/// Controls at the top of a page on one surface in the footer's style (experimental design): the
/// same frosted fill, light rim and shadow rule as the footer's buttons ([GlassStyle]). Several icon
/// buttons share one capsule, and a pressed one grows on its own while the capsule stays still; a
/// single button sits in a circle that grows as a whole. The buttons inside paint no circle of
/// their own.
class TopBarGlass extends StatelessWidget {
  const TopBarGlass({super.key, required this.children, this.height = 40});

  final List<Widget> children;
  final double height;

  @override
  Widget build(BuildContext context) {
    // The surface's own growth is the press feedback: no ink ring around it as well.
    return Theme(
      data: Theme.of(context).copyWith(
        splashFactory: NoSplash.splashFactory,
        splashColor: Colors.transparent,
        highlightColor: Colors.transparent,
        hoverColor: Colors.transparent,
      ),
      child: _build(context),
    );
  }

  Widget _build(BuildContext context) {
    if (children.length == 1) return FooterGlassSurface(height: height, circle: true, child: children.single);
    // The buttons are drawn over the capsule, not inside it: the capsule clips what it holds (for
    // its blur), and a pressed button's bubble rises past the capsule's edge.
    return Stack(
      clipBehavior: Clip.none,
      alignment: Alignment.center,
      children: [
        Positioned.fill(
          child: Center(child: FooterGlassSurface(height: height, swell: false, child: const SizedBox.expand())),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 2),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [for (final child in children) GlassPressItem(child: child)],
          ),
        ),
      ],
    );
  }
}
