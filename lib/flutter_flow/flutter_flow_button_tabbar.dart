import 'dart:math' as math;
import 'dart:ui' show lerpDouble;

import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart' show DragStartBehavior;
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';

const double _kTabHeight = 46.0;

typedef _LayoutCallback = void Function(
    List<double> xOffsets, TextDirection textDirection, double width);

class _TabLabelBarRenderer extends RenderFlex {
  _TabLabelBarRenderer({
    required Axis direction,
    required MainAxisSize mainAxisSize,
    required MainAxisAlignment mainAxisAlignment,
    required CrossAxisAlignment crossAxisAlignment,
    required TextDirection textDirection,
    required VerticalDirection verticalDirection,
    required this.onPerformLayout,
  }) : super(
          direction: direction,
          mainAxisSize: mainAxisSize,
          mainAxisAlignment: mainAxisAlignment,
          crossAxisAlignment: crossAxisAlignment,
          textDirection: textDirection,
          verticalDirection: verticalDirection,
        );

  _LayoutCallback onPerformLayout;

  @override
  void performLayout() {
    super.performLayout();
    // xOffsets will contain childCount+1 values, giving the offsets of the
    // leading edge of the first tab as the first value, of the leading edge of
    // the each subsequent tab as each subsequent value, and of the trailing
    // edge of the last tab as the last value.
    RenderBox? child = firstChild;
    final List<double> xOffsets = <double>[];
    while (child != null) {
      final FlexParentData childParentData =
          child.parentData! as FlexParentData;
      xOffsets.add(childParentData.offset.dx);
      assert(child.parentData == childParentData);
      child = childParentData.nextSibling;
    }
    assert(textDirection != null);
    switch (textDirection!) {
      case TextDirection.rtl:
        xOffsets.insert(0, size.width);
        break;
      case TextDirection.ltr:
        xOffsets.add(size.width);
        break;
    }
    onPerformLayout(xOffsets, textDirection!, size.width);
  }
}

// This class and its renderer class only exist to report the widths of the tabs
// upon layout. The tab widths are only used at paint time (see _IndicatorPainter)
// or in response to input.
class _TabLabelBar extends Flex {
  _TabLabelBar({
    required List<Widget> children,
    required this.onPerformLayout,
  }) : super(
          children: children,
          direction: Axis.horizontal,
          mainAxisSize: MainAxisSize.max,
          mainAxisAlignment: MainAxisAlignment.start,
          crossAxisAlignment: CrossAxisAlignment.center,
          verticalDirection: VerticalDirection.down,
        );

  final _LayoutCallback onPerformLayout;

  @override
  RenderFlex createRenderObject(BuildContext context) {
    return _TabLabelBarRenderer(
      direction: direction,
      mainAxisAlignment: mainAxisAlignment,
      mainAxisSize: mainAxisSize,
      crossAxisAlignment: crossAxisAlignment,
      textDirection: getEffectiveTextDirection(context)!,
      verticalDirection: verticalDirection,
      onPerformLayout: onPerformLayout,
    );
  }

  @override
  void updateRenderObject(
      BuildContext context, _TabLabelBarRenderer renderObject) {
    super.updateRenderObject(context, renderObject);
    renderObject.onPerformLayout = onPerformLayout;
  }
}

class _IndicatorPainter extends CustomPainter {
  _IndicatorPainter({
    required this.controller,
    required this.tabKeys,
    required _IndicatorPainter? old,
  }) : super(repaint: controller.animation) {
    if (old != null) {
      saveTabOffsets(old._currentTabOffsets, old._currentTextDirection);
    }
  }

  final TabController controller;

  final List<GlobalKey> tabKeys;

  // _currentTabOffsets and _currentTextDirection are set each time TabBar
  // layout is completed. These values can be null when TabBar contains no
  // tabs, since there are nothing to lay out.
  List<double>? _currentTabOffsets;
  TextDirection? _currentTextDirection;

  BoxPainter? _painter;
  bool _needsPaint = false;
  void markNeedsPaint() {
    _needsPaint = true;
  }

  void dispose() {
    _painter?.dispose();
  }

  void saveTabOffsets(List<double>? tabOffsets, TextDirection? textDirection) {
    _currentTabOffsets = tabOffsets;
    _currentTextDirection = textDirection;
  }

  // _currentTabOffsets[index] is the offset of the start edge of the tab at index, and
  // _currentTabOffsets[_currentTabOffsets.length] is the end edge of the last tab.
  int get maxTabIndex => _currentTabOffsets!.length - 2;

  double centerOf(int tabIndex) {
    assert(_currentTabOffsets != null);
    assert(_currentTabOffsets!.isNotEmpty);
    assert(tabIndex >= 0);
    assert(tabIndex <= maxTabIndex);
    return (_currentTabOffsets![tabIndex] + _currentTabOffsets![tabIndex + 1]) /
        2.0;
  }

  @override
  void paint(Canvas canvas, Size size) {
    _needsPaint = false;
  }

  @override
  bool shouldRepaint(_IndicatorPainter old) {
    return _needsPaint ||
        controller != old.controller ||
        tabKeys.length != old.tabKeys.length ||
        (!listEquals(_currentTabOffsets, old._currentTabOffsets)) ||
        _currentTextDirection != old._currentTextDirection;
  }
}

// This class, and TabBarScrollController, only exist to handle the case
// where a scrollable TabBar has a non-zero initialIndex. In that case we can
// only compute the scroll position's initial scroll offset (the "correct"
// pixels value) after the TabBar viewport width and scroll limits are known.

class _TabBarScrollPosition extends ScrollPositionWithSingleContext {
  _TabBarScrollPosition({
    required ScrollPhysics physics,
    required ScrollContext context,
    required ScrollPosition? oldPosition,
    required this.tabBar,
  }) : super(
          initialPixels: null,
          physics: physics,
          context: context,
          oldPosition: oldPosition,
        );

  final _FlutterFlowButtonTabBarState tabBar;

  bool _viewportDimensionWasNonZero = false;

  // Position should be adjusted at least once.
  bool _needsPixelsCorrection = true;

  @override
  bool applyContentDimensions(double minScrollExtent, double maxScrollExtent) {
    bool result = true;
    if (!_viewportDimensionWasNonZero) {
      _viewportDimensionWasNonZero = viewportDimension != 0.0;
    }
    // If the viewport never had a non-zero dimension, we just want to jump
    // to the initial scroll position to avoid strange scrolling effects in
    // release mode: In release mode, the viewport temporarily may have a
    // dimension of zero before the actual dimension is calculated. In that
    // scenario, setting the actual dimension would cause a strange scroll
    // effect without this guard because the super call below would starts a
    // ballistic scroll activity.
    if (!_viewportDimensionWasNonZero || _needsPixelsCorrection) {
      _needsPixelsCorrection = false;
      correctPixels(tabBar._initialScrollOffset(
          viewportDimension, minScrollExtent, maxScrollExtent));
      result = false;
    }
    return super.applyContentDimensions(minScrollExtent, maxScrollExtent) &&
        result;
  }

  void markNeedsPixelsCorrection() {
    _needsPixelsCorrection = true;
  }
}

// This class, and TabBarScrollPosition, only exist to handle the case
// where a scrollable TabBar has a non-zero initialIndex.
class _TabBarScrollController extends ScrollController {
  _TabBarScrollController(this.tabBar);

  final _FlutterFlowButtonTabBarState tabBar;

  @override
  ScrollPosition createScrollPosition(ScrollPhysics physics,
      ScrollContext context, ScrollPosition? oldPosition) {
    return _TabBarScrollPosition(
      physics: physics,
      context: context,
      oldPosition: oldPosition,
      tabBar: tabBar,
    );
  }
}

/// A Flutterflow Design widget that displays a horizontal row of tabs.
class FlutterFlowButtonTabBar extends StatefulWidget
    implements PreferredSizeWidget {
  /// The [tabs] argument must not be null and its length must match the [controller]'s
  /// [TabController.length].
  ///
  /// If a [TabController] is not provided, then there must be a
  /// [DefaultTabController] ancestor.
  ///
  const FlutterFlowButtonTabBar({
    Key? key,
    required this.tabs,
    this.controller,
    this.isScrollable = false,
    this.useToggleButtonStyle = false,
    this.dragStartBehavior = DragStartBehavior.start,
    this.onTap,
    this.backgroundColor,
    this.unselectedBackgroundColor,
    this.decoration,
    this.unselectedDecoration,
    this.labelStyle,
    this.unselectedLabelStyle,
    this.labelColor,
    this.unselectedLabelColor,
    this.borderWidth = 0,
    this.borderColor = Colors.transparent,
    this.unselectedBorderColor = Colors.transparent,
    this.physics = const BouncingScrollPhysics(),
    this.labelPadding = const EdgeInsets.symmetric(horizontal: 4),
    this.buttonMargin = const EdgeInsets.all(4),
    this.padding = EdgeInsets.zero,
    this.borderRadius = 8.0,
    this.elevation = 0,
  }) : super(key: key);

  /// Typically a list of two or more [Tab] widgets.
  ///
  /// The length of this list must match the [controller]'s [TabController.length]
  /// and the length of the [TabBarView.children] list.
  final List<Widget> tabs;

  /// This widget's selection and animation state.
  ///
  /// If [TabController] is not provided, then the value of [DefaultTabController.of]
  /// will be used.
  final TabController? controller;

  /// Whether this tab bar can be scrolled horizontally.
  ///
  /// If [isScrollable] is true, then each tab is as wide as needed for its label
  /// and the entire [FlutterFlowButtonTabBar] is scrollable. Otherwise each tab gets an equal
  /// share of the available space.
  final bool isScrollable;

  /// Whether the tab buttons should be styled as toggle buttons.
  final bool useToggleButtonStyle;

  /// The background [Color] of the button on its selected state.
  final Color? backgroundColor;

  /// The background [Color] of the button on its unselected state.
  final Color? unselectedBackgroundColor;

  /// The [BoxDecoration] of the button on its selected state.
  ///
  /// If [BoxDecoration] is not provided, [backgroundColor] is used.
  final BoxDecoration? decoration;

  /// The [BoxDecoration] of the button on its unselected state.
  ///
  /// If [BoxDecoration] is not provided, [unselectedBackgroundColor] is used.
  final BoxDecoration? unselectedDecoration;

  /// The [TextStyle] of the button's [Text] on its selected state. The color provided
  /// on the TextStyle will be used for the [Icon]'s color.
  final TextStyle? labelStyle;

  /// The color of selected tab labels.
  final Color? labelColor;

  /// The color of unselected tab labels.
  final Color? unselectedLabelColor;

  /// The [TextStyle] of the button's [Text] on its unselected state. The color provided
  /// on the TextStyle will be used for the [Icon]'s color.
  final TextStyle? unselectedLabelStyle;

  /// The with of solid [Border] for each button. If no value is provided, the border
  /// is not drawn.
  final double borderWidth;

  /// The [Color] of solid [Border] for each button.
  final Color? borderColor;

  /// The [Color] of solid [Border] for each button. If no value is provided, the value of
  /// [this.borderColor] is used.
  final Color? unselectedBorderColor;

  /// The [EdgeInsets] used for the [Padding] of the buttons' content.
  ///
  /// The default value is [EdgeInsets.symmetric(horizontal: 4)].
  final EdgeInsetsGeometry labelPadding;

  /// The [EdgeInsets] used for the [Margin] of the buttons.
  ///
  /// The default value is [EdgeInsets.all(4)].
  final EdgeInsetsGeometry buttonMargin;

  /// The amount of space by which to inset the tab bar.
  final EdgeInsetsGeometry? padding;

  /// The value of the [BorderRadius.circular] applied to each button.
  final double borderRadius;

  /// The value of the [elevation] applied to each button.
  final double elevation;

  final DragStartBehavior dragStartBehavior;

  final ValueChanged<int>? onTap;

  final ScrollPhysics? physics;

  /// A size whose height depends on if the tabs have both icons and text.
  ///
  /// [AppBar] uses this size to compute its own preferred size.
  @override
  Size get preferredSize {
    double maxHeight = _kTabHeight;
    for (final Widget item in tabs) {
      if (item is PreferredSizeWidget) {
        final double itemHeight = item.preferredSize.height;
        maxHeight = math.max(itemHeight, maxHeight);
      }
    }
    return Size.fromHeight(
        maxHeight + labelPadding.vertical + buttonMargin.vertical);
  }

  @override
  State<FlutterFlowButtonTabBar> createState() =>
      _FlutterFlowButtonTabBarState();
}

class _FlutterFlowButtonTabBarState extends State<FlutterFlowButtonTabBar>
    with TickerProviderStateMixin {
  ScrollController? _scrollController;
  TabController? _controller;
  _IndicatorPainter? _indicatorPainter;
  late AnimationController _animationController;
  int _currentIndex = 0;
  int _prevIndex = -1;

  late double _tabStripWidth;
  late List<GlobalKey> _tabKeys;

  final GlobalKey _tabsParentKey = GlobalKey();

  bool _debugHasScheduledValidTabsCountCheck = false;

  @override
  void initState() {
    super.initState();
    // If indicatorSize is TabIndicatorSize.label, _tabKeys[i] is used to find
    // the width of tab widget i. See _IndicatorPainter.indicatorRect().
    _tabKeys = widget.tabs.map((tab) => GlobalKey()).toList();

    /// The animation duration is 2/3 of the tab scroll animation duration in
    /// Material design (kTabScrollDuration).
    _animationController = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 200));

    // so the buttons start in their "final" state (color)
    _animationController
      ..value = 1.0
      ..addListener(() {
        if (mounted) {
          setState(() {});
        }
      });
  }

  // If the TabBar is rebuilt with a new tab controller, the caller should
  // dispose the old one. In that case the old controller's animation will be
  // null and should not be accessed.
  bool get _controllerIsValid => _controller?.animation != null;

  void _updateTabController() {
    final TabController? newController =
        widget.controller ?? DefaultTabController.maybeOf(context);
    assert(() {
      if (newController == null) {
        throw FlutterError(
          'No TabController for ${widget.runtimeType}.\n'
          'When creating a ${widget.runtimeType}, you must either provide an explicit '
          'TabController using the "controller" property, or you must ensure that there '
          'is a DefaultTabController above the ${widget.runtimeType}.\n'
          'In this case, there was neither an explicit controller nor a default controller.',
        );
      }
      return true;
    }());

    if (newController == _controller) {
      return;
    }

    if (_controllerIsValid) {
      _controller!.animation!.removeListener(_handleTabControllerAnimationTick);
      _controller!.removeListener(_handleTabControllerTick);
    }
    _controller = newController;
    if (_controller != null) {
      _controller!.animation!.addListener(_handleTabControllerAnimationTick);
      _controller!.addListener(_handleTabControllerTick);
      _currentIndex = _controller!.index;
    }
  }

  void _initIndicatorPainter() {
    _indicatorPainter = !_controllerIsValid
        ? null
        : _IndicatorPainter(
            controller: _controller!,
            tabKeys: _tabKeys,
            old: _indicatorPainter,
          );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    assert(debugCheckHasMaterial(context));
    _updateTabController();
    _initIndicatorPainter();
  }

  @override
  void didUpdateWidget(FlutterFlowButtonTabBar oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.controller != oldWidget.controller) {
      _updateTabController();
      _initIndicatorPainter();
      // Adjust scroll position.
      if (_scrollController != null) {
        final ScrollPosition position = _scrollController!.position;
        if (position is _TabBarScrollPosition) {
          position.markNeedsPixelsCorrection();
        }
      }
    }

    if (widget.tabs.length > _tabKeys.length) {
      final int delta = widget.tabs.length - _tabKeys.length;
      _tabKeys.addAll(List<GlobalKey>.generate(delta, (int n) => GlobalKey()));
    } else if (widget.tabs.length < _tabKeys.length) {
      _tabKeys.removeRange(widget.tabs.length, _tabKeys.length);
    }
  }

  @override
  void dispose() {
    _indicatorPainter!.dispose();
    if (_controllerIsValid) {
      _controller!.animation!.removeListener(_handleTabControllerAnimationTick);
      _controller!.removeListener(_handleTabControllerTick);
    }
    _controller = null;
    // We don't own the _controller Animation, so it's not disposed here.
    super.dispose();
  }

  int get maxTabIndex => _indicatorPainter!.maxTabIndex;

  double _tabScrollOffset(
      int index, double viewportWidth, double minExtent, double maxExtent) {
    if (!widget.isScrollable) {
      return 0.0;
    }
    double tabCenter = _indicatorPainter!.centerOf(index);
    double paddingStart;
    switch (Directionality.of(context)) {
      case TextDirection.rtl:
        paddingStart = widget.padding?.resolve(TextDirection.rtl).right ?? 0;
        tabCenter = _tabStripWidth - tabCenter;
        break;
      case TextDirection.ltr:
        paddingStart = widget.padding?.resolve(TextDirection.ltr).left ?? 0;
        break;
    }

    return clampDouble(
        tabCenter + paddingStart - viewportWidth / 2.0, minExtent, maxExtent);
  }

  double _tabCenteredScrollOffset(int index) {
    final ScrollPosition position = _scrollController!.position;
    return _tabScrollOffset(index, position.viewportDimension,
        position.minScrollExtent, position.maxScrollExtent);
  }

  double _initialScrollOffset(
      double viewportWidth, double minExtent, double maxExtent) {
    return _tabScrollOffset(_currentIndex, viewportWidth, minExtent, maxExtent);
  }

  void _scrollToCurrentIndex() {
    final double offset = _tabCenteredScrollOffset(_currentIndex);
    _scrollController!
        .animateTo(offset, duration: kTabScrollDuration, curve: Curves.ease);
  }

  void _scrollToControllerValue() {
    final double? leadingPosition =
        _currentIndex > 0 ? _tabCenteredScrollOffset(_currentIndex - 1) : null;
    final double middlePosition = _tabCenteredScrollOffset(_currentIndex);
    final double? trailingPosition = _currentIndex < maxTabIndex
        ? _tabCenteredScrollOffset(_currentIndex + 1)
        : null;

    final double index = _controller!.index.toDouble();
    final double value = _controller!.animation!.value;
    final double offset;
    if (value == index - 1.0) {
      offset = leadingPosition ?? middlePosition;
    } else if (value == index + 1.0) {
      offset = trailingPosition ?? middlePosition;
    } else if (value == index) {
      offset = middlePosition;
    } else if (value < index) {
      offset = leadingPosition == null
          ? middlePosition
          : lerpDouble(middlePosition, leadingPosition, index - value)!;
    } else {
      offset = trailingPosition == null
          ? middlePosition
          : lerpDouble(middlePosition, trailingPosition, value - index)!;
    }

    _scrollController!.jumpTo(offset);
  }

  void _handleTabControllerAnimationTick() {
    assert(mounted);
    if (!_controller!.indexIsChanging && widget.isScrollable) {
      // Sync the TabBar's scroll position with the TabBarView's PageView.
      _currentIndex = _controller!.index;
      _scrollToControllerValue();
    }
  }

  void _handleTabControllerTick() {
    if (_controller!.index != _currentIndex) {
      _prevIndex = _currentIndex;
      _currentIndex = _controller!.index;
      _triggerAnimation();
      if (widget.isScrollable) {
        _scrollToCurrentIndex();
      }
    }
    setState(() {
      // Rebuild the tabs after a (potentially animated) index change
      // has completed.
    });
  }

  void _triggerAnimation() {
    // reset the animation so it's ready to go
    _animationController
      ..reset()
      ..forward();
  }

  // Called each time layout completes.
  void _saveTabOffsets(
      List<double> tabOffsets, TextDirection textDirection, double width) {
    _tabStripWidth = width;
    _indicatorPainter?.saveTabOffsets(tabOffsets, textDirection);
  }

  void _handleTap(int index) {
    assert(index >= 0 && index < widget.tabs.length);
    _controller?.animateTo(index);
    widget.onTap?.call(index);
  }

  Widget _buildStyledTab(Widget child, int index) {
    final TabBarTheme tabBarTheme = TabBarTheme.of(context);

    final double animationValue;
    if (index == _currentIndex) {
      animationValue = _animationController.value;
    } else if (index == _prevIndex) {
      animationValue = 1 - _animationController.value;
    } else {
      animationValue = 0;
    }

    final TextStyle? textStyle = TextStyle.lerp(
        (widget.unselectedLabelStyle ??
                tabBarTheme.labelStyle ??
                DefaultTextStyle.of(context).style)
            .copyWith(
          color: widget.unselectedLabelColor,
        ),
        (widget.labelStyle ??
                tabBarTheme.labelStyle ??
                DefaultTextStyle.of(context).style)
            .copyWith(
          color: widget.labelColor,
        ),
        animationValue);

    final Color? textColor = Color.lerp(
        widget.unselectedLabelColor, widget.labelColor, animationValue);

    final Color? borderColor = Color.lerp(
        widget.unselectedBorderColor, widget.borderColor, animationValue);

    BoxDecoration? boxDecoration = BoxDecoration.lerp(
        BoxDecoration(
          color: widget.unselectedDecoration?.color ??
              widget.unselectedBackgroundColor ??
              Colors.transparent,
          boxShadow: widget.unselectedDecoration?.boxShadow,
          gradient: widget.unselectedDecoration?.gradient,
          borderRadius: widget.useToggleButtonStyle
              ? null
              : BorderRadius.circular(widget.borderRadius),
        ),
        BoxDecoration(
          color: widget.decoration?.color ??
              widget.backgroundColor ??
              Colors.transparent,
          boxShadow: widget.decoration?.boxShadow,
          gradient: widget.decoration?.gradient,
          borderRadius: widget.useToggleButtonStyle
              ? null
              : BorderRadius.circular(widget.borderRadius),
        ),
        animationValue);

    if (widget.useToggleButtonStyle &&
        widget.borderWidth > 0 &&
        boxDecoration != null) {
      if (index == 0) {
        boxDecoration = boxDecoration.copyWith(
          border: Border(
            right: BorderSide(
              color: widget.unselectedBorderColor ?? Colors.transparent,
              width: widget.borderWidth / 2,
            ),
          ),
        );
      } else if (index == widget.tabs.length - 1) {
        boxDecoration = boxDecoration.copyWith(
          border: Border(
            left: BorderSide(
              color: widget.unselectedBorderColor ?? Colors.transparent,
              width: widget.borderWidth / 2,
            ),
          ),
        );
      } else {
        boxDecoration = boxDecoration.copyWith(
          border: Border.symmetric(
            vertical: BorderSide(
              color: widget.unselectedBorderColor ?? Colors.transparent,
              width: widget.borderWidth / 2,
            ),
          ),
        );
      }
    }

    return Padding(
      key: _tabKeys[index],
      // padding for the buttons
      padding:
          widget.useToggleButtonStyle ? EdgeInsets.zero : widget.buttonMargin,
      child: TextButton(
        onPressed: () => _handleTap(index),
        style: ButtonStyle(
          elevation: MaterialStateProperty.all(
              widget.useToggleButtonStyle ? 0 : widget.elevation),

          /// give a pretty small minimum size
          minimumSize: MaterialStateProperty.all(const Size(10, 10)),
          padding: MaterialStateProperty.all(EdgeInsets.zero),
          textStyle: MaterialStateProperty.all(textStyle),
          foregroundColor: MaterialStateProperty.all(textColor),
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
          shape: MaterialStateProperty.all(
            widget.useToggleButtonStyle
                ? const RoundedRectangleBorder(
                    side: BorderSide.none,
                    borderRadius: BorderRadius.zero,
                  )
                : RoundedRectangleBorder(
                    side: (widget.borderWidth == 0)
                        ? BorderSide.none
                        : BorderSide(
                            color: borderColor ?? Colors.transparent,
                            width: widget.borderWidth,
                          ),
                    borderRadius: BorderRadius.circular(widget.borderRadius),
                  ),
          ),
        ),
        child: Ink(
          decoration: boxDecoration,
          child: Container(
            padding: widget.labelPadding,
            alignment: Alignment.center,
            child: child,
          ),
        ),
      ),
    );
  }

  bool _debugScheduleCheckHasValidTabsCount() {
    if (_debugHasScheduledValidTabsCountCheck) {
      return true;
    }
    WidgetsBinding.instance.addPostFrameCallback((Duration duration) {
      _debugHasScheduledValidTabsCountCheck = false;
      if (!mounted) {
        return;
      }
      assert(() {
        if (_controller!.length != widget.tabs.length) {
          throw FlutterError(
            "Controller's length property (${_controller!.length}) does not match the "
            "number of tabs (${widget.tabs.length}) present in TabBar's tabs property.",
          );
        }
        return true;
      }());
    });
    _debugHasScheduledValidTabsCountCheck = true;
    return true;
  }

  @override
  Widget build(BuildContext context) {
    assert(_debugScheduleCheckHasValidTabsCount());

    if (_controller!.length == 0) {
      return Container(
        height: _kTabHeight +
            widget.labelPadding.vertical +
            widget.buttonMargin.vertical,
      );
    }

    final List<Widget> wrappedTabs =
        List<Widget>.generate(widget.tabs.length, (int index) {
      return _buildStyledTab(widget.tabs[index], index);
    });

    final int tabCount = widget.tabs.length;
    // Add the tap handler to each tab. If the tab bar is not scrollable,
    // then give all of the tabs equal flexibility so that they each occupy
    // the same share of the tab bar's overall width.

    for (int index = 0; index < tabCount; index += 1) {
      if (!widget.isScrollable) {
        wrappedTabs[index] = Expanded(child: wrappedTabs[index]);
      }
    }

    Widget tabBar = AnimatedBuilder(
      animation: _animationController,
      key: _tabsParentKey,
      builder: (context, child) {
        Widget tabBarTemp = _TabLabelBar(
          onPerformLayout: _saveTabOffsets,
          children: wrappedTabs,
        );

        if (widget.useToggleButtonStyle) {
          tabBarTemp = Material(
            shape: widget.useToggleButtonStyle
                ? RoundedRectangleBorder(
                    side: (widget.borderWidth == 0)
                        ? BorderSide.none
                        : BorderSide(
                            color: widget.borderColor ?? Colors.transparent,
                            width: widget.borderWidth,
                            style: BorderStyle.solid,
                          ),
                    borderRadius: BorderRadius.circular(widget.borderRadius),
                  )
                : null,
            elevation: widget.useToggleButtonStyle ? widget.elevation : 0,
            clipBehavior: Clip.antiAliasWithSaveLayer,
            child: tabBarTemp,
          );
        }
        return CustomPaint(
          painter: _indicatorPainter,
          child: tabBarTemp,
        );
      },
    );

    if (widget.isScrollable) {
      _scrollController ??= _TabBarScrollController(this);
      tabBar = SingleChildScrollView(
        dragStartBehavior: widget.dragStartBehavior,
        scrollDirection: Axis.horizontal,
        controller: _scrollController,
        padding: widget.padding,
        physics: widget.physics,
        child: tabBar,
      );
    } else if (widget.padding != null) {
      tabBar = Padding(
        padding: widget.padding!,
        child: tabBar,
      );
    }

    return tabBar;
  }
}
