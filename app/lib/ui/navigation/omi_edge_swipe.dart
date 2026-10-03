import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

mixin OmiEdgeSwipeRoute<T> on PageRoute<T> {
  NavigatorState? _edgeNavigator;
  bool _edgeDragging = false;
  bool _edgeReduceMotion = false;
  double _edgeWidth = 1;

  bool get edgeSwipeInProgress => _edgeNavigator != null;

  Widget wrapEdgeSwipe(BuildContext context, Widget child) {
    if (Theme.of(context).platform != TargetPlatform.iOS) return child;
    final edge = 32 + MediaQuery.paddingOf(context).left;
    return Stack(
      fit: StackFit.expand,
      children: [
        child,
        Positioned(
          left: 0,
          top: 0,
          bottom: 0,
          width: edge,
          child: GestureDetector(
            behavior: HitTestBehavior.translucent,
            dragStartBehavior: DragStartBehavior.down,
            onHorizontalDragStart: (_) => _startEdgeSwipe(context),
            onHorizontalDragUpdate: (details) => _updateEdgeSwipe(details.delta.dx),
            onHorizontalDragEnd: (details) => _finishEdgeSwipe(details.primaryVelocity ?? 0),
            onHorizontalDragCancel: () => _finishEdgeSwipe(0, cancelled: true),
          ),
        ),
      ],
    );
  }

  bool _startEdgeSwipe(BuildContext context) {
    final owner = navigator;
    if (!isCurrent ||
        isFirst ||
        willHandlePopInternally ||
        popDisposition != RoutePopDisposition.pop ||
        _edgeNavigator != null ||
        controller?.status != AnimationStatus.completed ||
        owner == null ||
        owner.userGestureInProgress) {
      return false;
    }
    _edgeWidth = MediaQuery.sizeOf(context).width;
    if (_edgeWidth <= 0) return false;
    _edgeReduceMotion = MediaQuery.maybeDisableAnimationsOf(context) ?? false;
    _edgeDragging = true;
    _edgeNavigator = owner..didStartUserGesture();
    return true;
  }

  void _updateEdgeSwipe(double delta) {
    if (!_edgeDragging || _edgeWidth <= 0) return;
    controller!.value = (controller!.value - delta / _edgeWidth).clamp(0.0, 1.0);
  }

  void _finishEdgeSwipe(double velocity, {bool cancelled = false}) {
    if (!_edgeDragging) return;
    _edgeDragging = false;
    final progress = controller!;
    final distance = (1 - progress.value) * _edgeWidth;
    final dismiss = isCurrent
        ? !cancelled &&
            !willHandlePopInternally &&
            popDisposition == RoutePopDisposition.pop &&
            ((distance >= _edgeWidth * .33 && velocity > -700) || (distance >= 32 && velocity >= 900))
        : !isActive;
    final travel = dismiss ? progress.value : 1 - progress.value;
    final duration = _edgeReduceMotion ? Duration.zero : Duration(milliseconds: (180 + 140 * travel).round());
    if (dismiss && isCurrent) navigator!.pop();
    final settling = dismiss
        ? progress.animateBack(0, duration: duration, curve: Curves.easeOutCubic)
        : progress.animateTo(1, duration: duration, curve: Curves.easeOutCubic);
    settling.whenCompleteOrCancel(_finishEdgeGesture);
  }

  void _finishEdgeGesture() {
    final owner = _edgeNavigator;
    _edgeNavigator = null;
    if (owner?.mounted ?? false) owner!.didStopUserGesture();
  }

  @mustCallSuper
  void disposeEdgeSwipe() {
    _edgeDragging = false;
    final owner = _edgeNavigator;
    _edgeNavigator = null;
    if (owner != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (owner.mounted) owner.didStopUserGesture();
      });
    }
  }
}
