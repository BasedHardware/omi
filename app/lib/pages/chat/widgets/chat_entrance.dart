import 'package:flutter/material.dart';

/// Exact offsets from the chat prototype, all on one 1.1-second entrance.
abstract final class ChatIntro {
  static const length = Duration(milliseconds: 1100);
  static const rise = Cubic(.2, .8, .2, 1);
  static const greeting = Interval(0, 500 / 1100, curve: rise);
  static const countLine = Interval(120 / 1100, 620 / 1100, curve: rise);
  static const question = Interval(500 / 1100, 1000 / 1100, curve: rise);
  static const suggestions = Interval(350 / 1100, 850 / 1100, curve: Curves.easeOut);
  static const composer = Interval(150 / 1100, 600 / 1100, curve: rise);

  /// The prototype's `1 - (1 - t)^3` count-up from 250 ms through 900 ms.
  static double countProgress(double timelineValue) {
    final elapsed = timelineValue * length.inMilliseconds;
    final progress = ((elapsed - 250) / 650).clamp(0.0, 1.0);
    final remaining = 1 - progress;
    return 1 - remaining * remaining * remaining;
  }
}

/// One timeline for the greeting, suggestions and composer. Ordinary rebuilds never replay it.
class ChatEntrance extends StatefulWidget {
  const ChatEntrance({super.key, required this.child, this.revision = 0});
  final Widget child;
  final int revision;

  static Animation<double>? animationOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<_ChatTimeline>()?.animation;
  @override
  State<ChatEntrance> createState() => _ChatEntranceState();
}

class _ChatEntranceState extends State<ChatEntrance> with SingleTickerProviderStateMixin {
  late final _controller = AnimationController(vsync: this, duration: ChatIntro.length);
  bool _started = false;

  void _start() {
    _started = true;
    if (MediaQuery.disableAnimationsOf(context)) {
      _controller.value = 1;
    } else {
      _controller.forward(from: 0);
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_started) {
      _start();
    } else if (MediaQuery.disableAnimationsOf(context)) {
      _controller.value = 1;
    }
  }

  @override
  void didUpdateWidget(ChatEntrance oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.revision != widget.revision) _start();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => _ChatTimeline(animation: _controller, child: widget.child);
}

class _ChatTimeline extends InheritedWidget {
  const _ChatTimeline({required this.animation, required super.child});
  final Animation<double> animation;
  @override
  bool updateShouldNotify(_ChatTimeline oldWidget) => animation != oldWidget.animation;
}

class ChatRise extends StatelessWidget {
  const ChatRise({super.key, required this.child, this.interval = ChatIntro.greeting, this.fadeOnly = false});
  final Widget child;
  final Interval interval;
  final bool fadeOnly;

  @override
  Widget build(BuildContext context) {
    final animation = ChatEntrance.animationOf(context);
    if (animation == null || MediaQuery.disableAnimationsOf(context)) return child;
    return AnimatedBuilder(
      animation: animation,
      child: child,
      builder: (context, child) {
        final t = interval.transform(animation.value);
        return Opacity(
          opacity: t,
          alwaysIncludeSemantics: true,
          child: Transform.translate(offset: Offset(0, fadeOnly ? 0 : 10 * (1 - t)), child: child),
        );
      },
    );
  }
}

/// Animates the existing composer as one stable subtree; its text/focus/voice owners do not change.
class ChatComposerEntrance extends StatelessWidget {
  const ChatComposerEntrance(
      {super.key, required this.child, this.bottom = false, this.maintainBottomViewPadding = false});
  final Widget child;
  final bool bottom;
  final bool maintainBottomViewPadding;
  @override
  Widget build(BuildContext context) => ChatRise(
      interval: ChatIntro.composer,
      child: SafeArea(bottom: bottom, maintainBottomViewPadding: maintainBottomViewPadding, child: child));
}
