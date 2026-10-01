import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';

import 'package:omi/pages/chat/page.dart';
import 'package:omi/ui/ui.dart';

/// How long the chat sheet takes to rise; it falls a little faster.
const Duration kChatSheetRiseDuration = Duration(milliseconds: 420);
const Duration kChatSheetFallDuration = Duration(milliseconds: 280);

/// Opens chat the way every entry point does (docs/ux-contract.md D1): the page underneath blurs
/// and dims while the chat sheet rises from the bottom edge. The sheet carries an OmiCloseButton,
/// closes on a swipe down on its header, and system back closes it.
Future<T?> openChatSheet<T>(BuildContext context, ChatPage page) {
  return Navigator.of(context).push<T>(ChatSheetRoute<T>(builder: (_) => page));
}

/// The chat sheet's route: not opaque, so the page underneath stays painted behind the blur.
class ChatSheetRoute<T> extends PageRoute<T> {
  ChatSheetRoute({required this.builder, super.settings}) : super(fullscreenDialog: true);

  final WidgetBuilder builder;
  NavigatorState? _gestureNavigator;
  bool _dragging = false;
  bool _reduceMotion = false;
  double _extent = 1;

  @override
  bool get opaque => false;

  @override
  bool get barrierDismissible => false;

  @override
  Color? get barrierColor => null;

  @override
  String? get barrierLabel => null;

  @override
  bool get maintainState => true;

  @override
  Duration get transitionDuration => kChatSheetRiseDuration;

  @override
  Duration get reverseTransitionDuration => kChatSheetFallDuration;

  @override
  Widget buildPage(BuildContext context, Animation<double> animation, Animation<double> secondaryAnimation) {
    return builder(context);
  }

  @override
  Widget buildTransitions(
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
    Widget child,
  ) {
    if (MediaQuery.maybeDisableAnimationsOf(context) ?? false) return child;
    return ChatSheetTransition(animation: animation, linearMotion: _gestureNavigator != null, child: child);
  }

  bool startDismissDrag({required double extent, required bool reduceMotion}) {
    if (!isCurrent ||
        isFirst ||
        willHandlePopInternally ||
        popDisposition != RoutePopDisposition.pop ||
        _gestureNavigator != null ||
        controller?.status != AnimationStatus.completed ||
        extent <= 0) {
      return false;
    }
    _extent = extent;
    _reduceMotion = reduceMotion;
    _dragging = true;
    _gestureNavigator = navigator!..didStartUserGesture();
    return true;
  }

  void updateDismissDrag(double delta) {
    if (!_dragging) return;
    controller!.value = (controller!.value - delta / _extent).clamp(0.0, 1.0);
  }

  void finishDismissDrag(double velocity, {bool cancelled = false}) {
    if (!_dragging) return;
    _dragging = false;
    final progress = controller!;
    final distance = (1 - progress.value) * _extent;
    final dismiss = isCurrent
        ? !cancelled &&
            !willHandlePopInternally &&
            popDisposition == RoutePopDisposition.pop &&
            ((distance >= _extent * .22 && velocity > -700) || (distance >= 32 && velocity >= 900))
        : !isActive;
    final travel = dismiss ? progress.value : 1 - progress.value;
    final duration = _reduceMotion ? Duration.zero : Duration(milliseconds: (180 + 140 * travel).round());
    if (dismiss && isCurrent) navigator!.pop();
    final settling = dismiss
        ? progress.animateBack(0, duration: duration, curve: Curves.easeOutCubic)
        : progress.animateTo(1, duration: duration, curve: Curves.easeOutCubic);
    settling.whenCompleteOrCancel(_finishGesture);
  }

  void _finishGesture() {
    final owner = _gestureNavigator;
    _gestureNavigator = null;
    if (owner?.mounted ?? false) owner!.didStopUserGesture();
  }

  @override
  void dispose() {
    _dragging = false;
    final owner = _gestureNavigator;
    _gestureNavigator = null;
    if (owner != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (owner.mounted) owner.didStopUserGesture();
      });
    }
    super.dispose();
  }
}

/// The rise itself, separate from the route so tests and the visual audit can pump one frame of it.
class ChatSheetTransition extends StatelessWidget {
  const ChatSheetTransition({
    super.key,
    required this.animation,
    required this.child,
    this.linearMotion = false,
  });

  final Animation<double> animation;
  final Widget child;
  final bool linearMotion;

  @override
  Widget build(BuildContext context) {
    // A soft landing: fast out of the bottom edge, settling without a bounce.
    final Animation<double> rise = linearMotion
        ? animation
        : CurvedAnimation(parent: animation, curve: Curves.easeOutQuart, reverseCurve: Curves.easeInCubic);
    final Animation<double> backdrop = linearMotion
        ? animation
        : CurvedAnimation(parent: animation, curve: Curves.easeOut, reverseCurve: Curves.easeIn);
    return Stack(
      fit: StackFit.expand,
      children: [
        // The page underneath goes soft and dim; it stays visible through the empty sheet.
        IgnorePointer(
          child: AnimatedBuilder(
            animation: backdrop,
            builder: (context, _) {
              final t = backdrop.value;
              return BackdropFilter(
                filter: ImageFilter.blur(sigmaX: 18 * t, sigmaY: 18 * t),
                child: ColoredBox(color: OmiColors.surface0.withValues(alpha: 0.55 * t)),
              );
            },
          ),
        ),
        SlideTransition(
          position: Tween<Offset>(begin: const Offset(0, 1), end: Offset.zero).animate(rise),
          child: FadeTransition(opacity: Tween<double>(begin: 0.6, end: 1).animate(rise), child: child),
        ),
      ],
    );
  }
}
