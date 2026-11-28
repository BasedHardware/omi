import 'dart:async';

import 'package:flutter/gestures.dart' show kTouchSlop;
import 'package:flutter/material.dart';

import 'package:omi/services/experiments/experimental_design.dart';
import 'package:omi/ui/ui.dart';

/// Experimental design: the pressed state of a Home list row.
///
/// The row has no card of its own, so a touch has to show somewhere: a rounded wash of the primary
/// ink comes up over the whole row and the row swells a little, the way the footer buttons answer a
/// touch. It leaves slowly when the finger lifts, so a quick tap is still seen.
///
/// It only watches pointers and takes no part in gestures: the row's own tap, long press and swipe
/// work as before. A touch that turns into a scroll or a swipe drops the state, and the short wait
/// before it shows keeps a scrolling list from flickering. Outside the experimental design, or with
/// [enabled] false, it is just [child].
class RowPress extends StatefulWidget {
  const RowPress({super.key, required this.child, this.enabled = true, this.borderRadius = OmiRadius.mdAll});

  final Widget child;
  final bool enabled;
  final BorderRadius borderRadius;

  /// How far the row swells while pressed.
  static const double pressedScale = 1.02;

  /// The wait before a touch shows, so the start of a scroll does not flash the row.
  static const Duration showDelay = Duration(milliseconds: 70);

  /// How long a tap that is over before [showDelay] still shows for.
  static const Duration tapHold = Duration(milliseconds: 120);

  @override
  State<RowPress> createState() => _RowPressState();
}

class _RowPressState extends State<RowPress> {
  bool _down = false;
  int? _pointer;
  Offset _origin = Offset.zero;
  Timer? _timer;

  void _set(bool down) {
    if (mounted && _down != down) setState(() => _down = down);
  }

  void _onDown(PointerDownEvent event) {
    if (_pointer != null) return;
    _pointer = event.pointer;
    _origin = event.position;
    _timer?.cancel();
    _timer = Timer(RowPress.showDelay, () => _set(true));
  }

  void _onMove(PointerMoveEvent event) {
    if (event.pointer != _pointer) return;
    if ((event.position - _origin).distance > kTouchSlop) _release(tapped: false);
  }

  void _onUp(PointerEvent event) {
    if (event.pointer == _pointer) _release(tapped: event is PointerUpEvent);
  }

  void _release({required bool tapped}) {
    final pending = _timer?.isActive ?? false;
    _timer?.cancel();
    _pointer = null;
    if (tapped && pending) {
      // The finger lifted before the wait was over: show the tap briefly.
      _set(true);
      _timer = Timer(RowPress.tapHold, () => _set(false));
    } else {
      _set(false);
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.enabled || !ExperimentalDesign.of(context)) return widget.child;
    final motion = OmiMotion.of(context);
    final dark = Theme.of(context).brightness == Brightness.dark;
    final wash = OmiColors.textPrimary.withValues(alpha: dark ? 0.12 : 0.06);
    // In quickly, out slowly.
    final duration = _down ? motion.quick : motion.standard;
    return Listener(
      onPointerDown: _onDown,
      onPointerMove: _onMove,
      onPointerUp: _onUp,
      onPointerCancel: _onUp,
      child: AnimatedScale(
        scale: _down ? RowPress.pressedScale : 1,
        duration: duration,
        curve: OmiMotion.emphasizedCurve,
        child: AnimatedContainer(
          duration: duration,
          curve: OmiMotion.emphasizedCurve,
          foregroundDecoration:
              BoxDecoration(color: _down ? wash : wash.withValues(alpha: 0), borderRadius: widget.borderRadius),
          child: widget.child,
        ),
      ),
    );
  }
}
