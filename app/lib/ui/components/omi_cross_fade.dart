// A cross-fade between keyed children that draws the bare child at rest; owns paying for opacity
// layers only while a change is on screen, so list rows stay inside the scroll budgets (performance.md).

import 'package:flutter/widgets.dart';

import 'package:omi/ui/omi_tokens.dart';

/// Fades the old child out and the new one in when [child]'s key or type changes. At rest it is
/// just [child]: no opacity layer, no stack, no clip, unlike [AnimatedSwitcher], which keeps a
/// fade layer on every row of a list. Under Reduce Motion the change is instant.
class OmiCrossFade extends StatefulWidget {
  const OmiCrossFade({super.key, required this.child, this.alignment = AlignmentDirectional.topStart});

  final Widget child;
  final AlignmentGeometry alignment;

  @override
  State<OmiCrossFade> createState() => _OmiCrossFadeState();
}

class _OmiCrossFadeState extends State<OmiCrossFade> with SingleTickerProviderStateMixin {
  /// Made on the first change, so a row that never changes holds no ticker.
  AnimationController? _controller;
  Widget? _previous;
  int _change = 0;

  @override
  void didUpdateWidget(OmiCrossFade oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (Widget.canUpdate(oldWidget.child, widget.child)) return;
    final duration = OmiMotion.of(context).standard;
    if (duration == Duration.zero) {
      _previous = null;
      return;
    }
    final change = ++_change;
    _previous = oldWidget.child;
    final controller = _controller ??= AnimationController(vsync: this);
    controller.duration = duration;
    controller.forward(from: 0).whenCompleteOrCancel(() {
      if (mounted && change == _change) setState(() => _previous = null);
    });
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final previous = _previous;
    final controller = _controller;
    if (previous == null || controller == null) return widget.child;
    return Stack(
      alignment: widget.alignment,
      clipBehavior: Clip.none,
      children: [
        FadeTransition(opacity: ReverseAnimation(controller), child: previous),
        FadeTransition(opacity: controller, child: widget.child),
      ],
    );
  }
}
