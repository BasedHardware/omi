import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';

/// Home and Tasks as an [IndexedStack] (both keep their state and scroll position), with the
/// page that comes in fading and sliding a short way from the side of its tab: Tasks from the
/// right, Home from the left. Reduce Motion switches without the animation.
class HomePageStack extends StatefulWidget {
  const HomePageStack({super.key, required this.index, required this.children});

  final int index;
  final List<Widget> children;

  @override
  State<HomePageStack> createState() => _HomePageStackState();
}

class _HomePageStackState extends State<HomePageStack> with SingleTickerProviderStateMixin {
  /// How far the incoming page travels, as a fraction of its width.
  static const _travel = 0.06;

  late final AnimationController _controller = AnimationController(vsync: this, value: 1);
  late final Animation<double> _fade = CurvedAnimation(parent: _controller, curve: OmiMotion.emphasizedCurve);
  late Animation<Offset> _slide = const AlwaysStoppedAnimation(Offset.zero);

  @override
  void didUpdateWidget(HomePageStack oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.index == oldWidget.index) return;
    final fromRight = widget.index > oldWidget.index;
    _slide = Tween(begin: Offset(fromRight ? _travel : -_travel, 0), end: Offset.zero).animate(_fade);
    _controller.duration = OmiMotion.of(context).standard;
    _controller.forward(from: 0);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Every child keeps the same wrapper types whether or not it is selected, so switching
    // never rebuilds a page's subtree; only the selected one is driven by the animation.
    return IndexedStack(
      index: widget.index,
      children: [
        for (var i = 0; i < widget.children.length; i++)
          FadeTransition(
            opacity: i == widget.index ? _fade : kAlwaysCompleteAnimation,
            child: SlideTransition(
              position: i == widget.index ? _slide : const AlwaysStoppedAnimation(Offset.zero),
              child: widget.children[i],
            ),
          ),
      ],
    );
  }
}
