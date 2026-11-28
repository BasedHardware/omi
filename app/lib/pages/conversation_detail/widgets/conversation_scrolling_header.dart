import 'dart:ui' show lerpDouble;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/scheduler.dart';

/// The conversation page's title, facts and tabs scrolling away with the open tab's content
/// (experimental design), instead of staying fixed above it.
///
/// The header is drawn over the tab pages, and each page starts with an empty space of the header's
/// height ([ConversationScrollingHeader.insetOf]), so the two move as one: the header is shifted up
/// by as far as the open page has scrolled. Each page keeps its own scroll position; between two
/// pages the shift follows the swipe.
class ConversationScrollingHeaderController {
  ConversationScrollingHeaderController(int tabs) : offsets = [for (var i = 0; i < tabs; i++) ValueNotifier(0)];

  /// The header's laid-out height; 0 until it has been laid out once.
  final ValueNotifier<double> height = ValueNotifier(0);

  /// How far each tab's page has scrolled from its top.
  final List<ValueNotifier<double>> offsets;

  void dispose() {
    height.dispose();
    for (final offset in offsets) {
      offset.dispose();
    }
  }
}

/// The tab pages under the header and the header over them. A touch that starts on the header
/// reaches the page under it as well, so a drag there scrolls the page.
class ConversationScrollingHeader extends StatelessWidget {
  const ConversationScrollingHeader({
    super.key,
    required this.controller,
    required this.tabAnimation,
    required this.header,
    required this.body,
  });

  final ConversationScrollingHeaderController controller;

  /// The TabController's animation: 0 for the first tab, 1 for the second, between while swiping.
  final Animation<double> tabAnimation;
  final Widget header;
  final Widget body;

  /// The space a tab page leaves at its top for the header; 0 when the header is fixed. The page
  /// rebuilds when the header's height changes.
  static double insetOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<_HeaderInset>()?.notifier?.value ?? 0;

  /// Wraps one tab page: reports how far its own vertical list has scrolled.
  static Widget tab(ConversationScrollingHeaderController controller, int index, Widget child) =>
      _TabOffsetReporter(offset: controller.offsets[index], child: child);

  double _shift() {
    final offsets = controller.offsets;
    final position = tabAnimation.value.clamp(0.0, offsets.length - 1.0);
    final from = position.floor();
    final to = position.ceil();
    final offset = lerpDouble(offsets[from].value, offsets[to].value, position - from)!;
    return offset.clamp(0.0, controller.height.value);
  }

  @override
  Widget build(BuildContext context) {
    return _HeaderInset(
      notifier: controller.height,
      child: ClipRect(
        child: _HitAllStack(
          children: [
            // Nothing is shown under the header until its height is known, one frame after the
            // first layout: the pages would otherwise start under it and jump down.
            Positioned.fill(
              child: ValueListenableBuilder<double>(
                valueListenable: controller.height,
                builder: (context, height, child) => Opacity(opacity: height > 0 ? 1 : 0, child: child),
                child: body,
              ),
            ),
            Positioned(
              top: 0,
              left: 0,
              right: 0,
              child: AnimatedBuilder(
                animation: Listenable.merge([tabAnimation, controller.height, ...controller.offsets]),
                builder: (context, child) => Transform.translate(offset: Offset(0, -_shift()), child: child),
                child: _SizeReporter(
                  onHeight: (height) => controller.height.value = height,
                  child: header,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// A tab page that can hold the header in place: while [pinned], something of its own is fixed above
/// its list (a labelling bar) or it has no list, so it leaves the header's space itself and reports
/// no scrolling. Unpinned, its list leaves that space ([ConversationScrollingHeader.insetOf]). The
/// widget keeps one shape either way, so the list under it keeps its place when a bar comes or goes.
class ConversationScrollingHeaderPinned extends StatefulWidget {
  const ConversationScrollingHeaderPinned({super.key, this.pinned = true, required this.child});

  final bool pinned;
  final Widget child;

  @override
  State<ConversationScrollingHeaderPinned> createState() => _ConversationScrollingHeaderPinnedState();
}

class _ConversationScrollingHeaderPinnedState extends State<ConversationScrollingHeaderPinned> {
  @override
  void initState() {
    super.initState();
    if (widget.pinned) _resetOffset();
  }

  @override
  void didUpdateWidget(ConversationScrollingHeaderPinned oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.pinned && !oldWidget.pinned) _resetOffset();
  }

  // The page may have been scrolled before it became pinned.
  void _resetOffset() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.findAncestorStateOfType<_TabOffsetReporterState>()?.reset();
    });
  }

  @override
  Widget build(BuildContext context) {
    final pinned = widget.pinned;
    final inset = pinned ? ConversationScrollingHeader.insetOf(context) : 0.0;
    return NotificationListener<ScrollMetricsNotification>(
      onNotification: (_) => pinned,
      child: NotificationListener<ScrollNotification>(
        onNotification: (_) => pinned,
        child: Padding(padding: EdgeInsets.only(top: inset), child: widget.child),
      ),
    );
  }
}

class _HeaderInset extends InheritedNotifier<ValueNotifier<double>> {
  const _HeaderInset({required super.notifier, required super.child});
}

class _TabOffsetReporter extends StatefulWidget {
  const _TabOffsetReporter({required this.offset, required this.child});

  final ValueNotifier<double> offset;
  final Widget child;

  @override
  State<_TabOffsetReporter> createState() => _TabOffsetReporterState();
}

class _TabOffsetReporterState extends State<_TabOffsetReporter> {
  void reset() => widget.offset.value = 0;

  void _report(ScrollMetrics metrics, int depth) {
    // The page's own list only: not a strip scrolling sideways, nor a list inside the list.
    if (depth != 0 || metrics.axis != Axis.vertical || !metrics.hasPixels || !metrics.hasContentDimensions) return;
    final offset = metrics.extentBefore;
    if (offset == widget.offset.value) return;
    // A layout can report new metrics; listeners must not rebuild in the middle of it.
    if (WidgetsBinding.instance.schedulerPhase == SchedulerPhase.persistentCallbacks) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) widget.offset.value = offset;
      });
    } else {
      widget.offset.value = offset;
    }
  }

  @override
  Widget build(BuildContext context) {
    return NotificationListener<ScrollMetricsNotification>(
      onNotification: (notification) {
        _report(notification.metrics, notification.depth);
        return false;
      },
      child: NotificationListener<ScrollNotification>(
        onNotification: (notification) {
          _report(notification.metrics, notification.depth);
          return false;
        },
        child: widget.child,
      ),
    );
  }
}

/// Reports its child's height after each layout that changes it.
class _SizeReporter extends SingleChildRenderObjectWidget {
  const _SizeReporter({required this.onHeight, required super.child});

  final ValueChanged<double> onHeight;

  @override
  RenderObject createRenderObject(BuildContext context) => _RenderSizeReporter(onHeight);

  @override
  void updateRenderObject(BuildContext context, _RenderSizeReporter renderObject) => renderObject.onHeight = onHeight;
}

class _RenderSizeReporter extends RenderProxyBox {
  _RenderSizeReporter(this.onHeight);

  ValueChanged<double> onHeight;
  double? _reported;

  @override
  void performLayout() {
    super.performLayout();
    final height = size.height;
    if (height == _reported) return;
    _reported = height;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (attached && _reported == height) onHeight(height);
    });
  }
}

/// A Stack whose every child under the touch receives it, not only the topmost.
class _HitAllStack extends Stack {
  const _HitAllStack({required super.children});

  @override
  RenderStack createRenderObject(BuildContext context) => _RenderHitAllStack(
        alignment: alignment,
        textDirection: textDirection ?? Directionality.maybeOf(context),
        fit: fit,
        clipBehavior: clipBehavior,
      );
}

class _RenderHitAllStack extends RenderStack {
  _RenderHitAllStack({super.alignment, super.textDirection, super.fit, super.clipBehavior});

  @override
  bool hitTestChildren(BoxHitTestResult result, {required Offset position}) {
    var hit = false;
    var child = lastChild;
    while (child != null) {
      final parentData = child.parentData! as StackParentData;
      final target = child;
      hit = result.addWithPaintOffset(
            offset: parentData.offset,
            position: position,
            hitTest: (result, transformed) => target.hitTest(result, position: transformed),
          ) ||
          hit;
      child = parentData.previousSibling;
    }
    return hit;
  }
}
