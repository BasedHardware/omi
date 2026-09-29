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
    return ChatSheetTransition(animation: animation, child: child);
  }
}

/// The rise itself, separate from the route so tests and the visual audit can pump one frame of it.
class ChatSheetTransition extends StatelessWidget {
  const ChatSheetTransition({super.key, required this.animation, required this.child});

  final Animation<double> animation;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    // A soft landing: fast out of the bottom edge, settling without a bounce.
    final rise = CurvedAnimation(parent: animation, curve: Curves.easeOutQuart, reverseCurve: Curves.easeInCubic);
    final backdrop = CurvedAnimation(parent: animation, curve: Curves.easeOut, reverseCurve: Curves.easeIn);
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
