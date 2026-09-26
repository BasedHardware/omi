import 'dart:async';

import 'package:clock/clock.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';

/// The amount of content that may remain below the viewport while a reader is
/// considered to be at the end of a document.
const double _bottomTolerance = 48.0;

/// A callback validator passed to the review service.
///
/// The service should call this immediately before requesting the platform
/// review prompt. It is deliberately a closure over the current presentation
/// attempt, so a late async continuation cannot use an old content identity.
typedef ReadingMomentValidator = bool Function();

/// Admits a review request after a user has had time to read a surface.
///
/// This widget only measures local UI state. It does not know how often a
/// user has been prompted or call the platform review API. Callers should do
/// those checks in [onFinishedReading], using the supplied validator again at
/// the last possible moment.
class ReviewReadingMoment extends StatefulWidget {
  const ReviewReadingMoment({
    super.key,
    required this.child,
    required this.contentId,
    required this.enabled,
    required this.onFinishedReading,
    this.onEngaged,
    this.minimumReadingDuration = const Duration(seconds: 15),
    this.bottomIdleDuration = const Duration(seconds: 2),
  });

  final Widget child;
  final String contentId;
  final bool enabled;
  final Future<void> Function(ReadingMomentValidator isStillAppropriate) onFinishedReading;
  final VoidCallback? onEngaged;

  /// Foreground, non-scrolling time required before a request is admitted.
  final Duration minimumReadingDuration;

  /// Time that the reader must remain settled at the end of the content.
  final Duration bottomIdleDuration;

  @override
  State<ReviewReadingMoment> createState() => _ReviewReadingMomentState();
}

class _ReviewReadingMomentState extends State<ReviewReadingMoment> with WidgetsBindingObserver {
  Timer? _readingTimer;
  Timer? _bottomIdleTimer;
  DateTime? _readingStartedAt;
  DateTime? _bottomIdleStartedAt;

  Duration _readingElapsed = Duration.zero;
  bool _metricsKnown = false;
  bool _contentFits = true;
  bool _atBottom = true;
  bool _hasGenuineUserScroll = false;
  bool _isScrolling = false;
  bool _didFinish = false;
  bool _didEngage = false;
  bool _routeIsCurrent = true;
  bool _tickerIsEnabled = true;
  bool _keyboardIsOpenCached = false;
  bool _wasVisibleAndEnabled = false;
  AppLifecycleState _lifecycle = AppLifecycleState.resumed;
  int _presentationGeneration = 0;

  ModalRoute<dynamic>? _observedRoute;
  Animation<double>? _routeAnimation;
  Animation<double>? _secondaryRouteAnimation;

  @override
  void initState() {
    super.initState();
    _lifecycle = WidgetsBinding.instance.lifecycleState ?? AppLifecycleState.resumed;
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();

    _tickerIsEnabled = TickerMode.valuesOf(context).enabled;
    _keyboardIsOpenCached = _readKeyboardIsOpen();
    final route = ModalRoute.of(context);
    _watchRoute(route);
    _updateRouteEligibility();
    _syncTimers();
    _scheduleEngagementCheck();
  }

  @override
  void didUpdateWidget(covariant ReviewReadingMoment oldWidget) {
    super.didUpdateWidget(oldWidget);

    if (oldWidget.contentId != widget.contentId) {
      _resetForNewContent();
    } else if (oldWidget.enabled != widget.enabled && !widget.enabled) {
      // Tab switches, editors, loading states, and share flows use enabled as
      // an explicit admission boundary. Do not let a timer armed before that
      // boundary survive into the next presentation.
      _resetReadingProgress();
    } else if (oldWidget.enabled != widget.enabled && widget.enabled) {
      _scheduleEngagementCheck();
    }

    if (oldWidget.minimumReadingDuration != widget.minimumReadingDuration ||
        oldWidget.bottomIdleDuration != widget.bottomIdleDuration) {
      _cancelTimers();
    }
    _syncTimers();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _lifecycle = state;
    if (state != AppLifecycleState.resumed) {
      _presentationGeneration++;
      _wasVisibleAndEnabled = false;
      _pauseReading();
      _resetBottomIdle();
    } else {
      _syncTimers();
      _scheduleEngagementCheck();
    }
  }

  @override
  void didChangeMetrics() {
    if (!mounted) return;
    final keyboardIsOpen = _readKeyboardIsOpen();
    if (keyboardIsOpen == _keyboardIsOpenCached) return;
    _keyboardIsOpenCached = keyboardIsOpen;
    _syncTimers();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _stopRouteWatching();
    _cancelTimers();
    super.dispose();
  }

  void _watchRoute(ModalRoute<dynamic>? route) {
    if (identical(route, _observedRoute)) return;

    _stopRouteWatching();
    _observedRoute = route;
    _routeAnimation = route?.animation;
    _secondaryRouteAnimation = route?.secondaryAnimation;
    _routeAnimation?.addListener(_onRouteTransition);
    _secondaryRouteAnimation?.addListener(_onRouteTransition);
  }

  void _stopRouteWatching() {
    _routeAnimation?.removeListener(_onRouteTransition);
    _secondaryRouteAnimation?.removeListener(_onRouteTransition);
    _routeAnimation = null;
    _secondaryRouteAnimation = null;
    _observedRoute = null;
  }

  void _onRouteTransition() {
    if (!mounted) return;
    _updateRouteEligibility();
    _syncTimers();
    _scheduleEngagementCheck();
  }

  bool _isCurrentRoute() => ModalRoute.of(context)?.isCurrent ?? true;

  bool _readKeyboardIsOpen() {
    return View.of(context).viewInsets.bottom > 0 || (MediaQuery.maybeOf(context)?.viewInsets.bottom ?? 0) > 0;
  }

  bool _keyboardIsOpen() => _keyboardIsOpenCached || _readKeyboardIsOpen();

  bool _routeTransitionIsSettled() {
    final primary = _routeAnimation;
    final secondary = _secondaryRouteAnimation;
    return (primary == null || primary.status == AnimationStatus.completed) &&
        (secondary == null || secondary.status == AnimationStatus.dismissed);
  }

  void _updateRouteEligibility() {
    final routeIsCurrent = _isCurrentRoute();
    if (routeIsCurrent == _routeIsCurrent) return;

    _routeIsCurrent = routeIsCurrent;
    if (!routeIsCurrent) {
      _presentationGeneration++;
      _wasVisibleAndEnabled = false;
    }
    _pauseReading();
    _resetBottomIdle();
  }

  bool _visibleAndEnabled() {
    return mounted &&
        widget.enabled &&
        _lifecycle == AppLifecycleState.resumed &&
        _routeIsCurrent &&
        _isCurrentRoute() &&
        _routeTransitionIsSettled() &&
        _tickerIsEnabled &&
        TickerMode.valuesOf(context).enabled &&
        !_keyboardIsOpen();
  }

  bool _contentCanFinish() {
    if (!_atBottom) return false;
    if (!_contentFits && !_hasGenuineUserScroll) return false;
    return _bottomIdleDurationMet || widget.bottomIdleDuration <= Duration.zero;
  }

  bool get _bottomIdleDurationMet {
    final startedAt = _bottomIdleStartedAt;
    return startedAt != null && clock.now().difference(startedAt) >= widget.bottomIdleDuration;
  }

  bool _isStillAppropriateFor(int generation) {
    if (!mounted || generation != _presentationGeneration) {
      return false;
    }
    if (!_visibleAndEnabled()) {
      if (_wasVisibleAndEnabled) {
        _presentationGeneration++;
        _wasVisibleAndEnabled = false;
      }
      return false;
    }
    if (_isScrolling || !_contentCanFinish()) return false;
    if (!_contentFits && !_hasGenuineUserScroll) return false;
    return true;
  }

  void _syncTimers() {
    final visibleAndEnabled = _visibleAndEnabled();
    if (!visibleAndEnabled) {
      if (_wasVisibleAndEnabled) {
        _presentationGeneration++;
      }
      _wasVisibleAndEnabled = false;
      _pauseReading();
      _resetBottomIdle();
      return;
    }

    _wasVisibleAndEnabled = true;

    // A scrollable child reports its extent through this notification. Waiting
    // for it avoids treating a retained, long list as a short document when a
    // content identity changes without rebuilding the list's scroll position.
    if (!_metricsKnown) {
      _pauseReading();
      _resetBottomIdle();
      return;
    }

    if (_isScrolling) {
      _pauseReading();
      _resetBottomIdle();
      return;
    }

    _startReading();
    if (_atBottom && (_contentFits || _hasGenuineUserScroll)) {
      _startBottomIdle();
    } else {
      _resetBottomIdle();
    }
  }

  void _startReading() {
    if (_readingElapsed >= widget.minimumReadingDuration || _readingStartedAt != null) {
      return;
    }

    _readingStartedAt = clock.now();
    final remaining = widget.minimumReadingDuration - _readingElapsed;
    _readingTimer?.cancel();
    _readingTimer = Timer(remaining, _onReadingTimer);
  }

  void _onReadingTimer() {
    _readingTimer = null;
    _pauseReading();
    _maybeFinish();
  }

  void _pauseReading() {
    final startedAt = _readingStartedAt;
    if (startedAt != null) {
      _readingElapsed += clock.now().difference(startedAt);
      _readingStartedAt = null;
    }
    _readingTimer?.cancel();
    _readingTimer = null;
  }

  void _startBottomIdle() {
    if (_bottomIdleStartedAt != null || _bottomIdleTimer != null) return;

    if (widget.bottomIdleDuration <= Duration.zero) {
      _bottomIdleStartedAt = clock.now();
      return;
    }
    _bottomIdleStartedAt = clock.now();
    _bottomIdleTimer = Timer(widget.bottomIdleDuration, _onBottomIdleTimer);
  }

  void _onBottomIdleTimer() {
    _bottomIdleTimer = null;
    _maybeFinish();
  }

  void _resetBottomIdle() {
    _bottomIdleStartedAt = null;
    _bottomIdleTimer?.cancel();
    _bottomIdleTimer = null;
  }

  void _cancelTimers() {
    _pauseReading();
    _resetBottomIdle();
  }

  void _resetReadingProgress() {
    _cancelTimers();
    _readingElapsed = Duration.zero;
    _hasGenuineUserScroll = false;
    _isScrolling = false;
    _presentationGeneration++;
  }

  void _resetForNewContent() {
    _resetReadingProgress();
    _didFinish = false;
    _didEngage = false;
    _metricsKnown = false;
    _contentFits = true;
    _atBottom = false;
  }

  void _scheduleEngagementCheck() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _didEngage || !_visibleAndEnabled()) return;
      _didEngage = true;
      widget.onEngaged?.call();
    });
  }

  void _maybeFinish() {
    if (_didFinish || !_readingDurationMet || !_contentCanFinish() || _isScrolling || !_visibleAndEnabled()) {
      _syncTimers();
      return;
    }

    final generation = _presentationGeneration;
    _didFinish = true;
    bool validator() => _isStillAppropriateFor(generation);
    unawaited(widget.onFinishedReading(validator));
  }

  bool get _readingDurationMet => _readingElapsed >= widget.minimumReadingDuration;

  bool _handleScrollNotification(ScrollNotification notification) {
    if (notification.depth != 0) return false;

    _updateMetrics(notification.metrics);
    if (notification is ScrollStartNotification) {
      _isScrolling = true;
      _resetBottomIdle();
      if (notification.dragDetails != null) {
        _hasGenuineUserScroll = true;
      }
    } else if (notification is ScrollUpdateNotification) {
      _isScrolling = true;
      _resetBottomIdle();
      if (notification.dragDetails != null) {
        _hasGenuineUserScroll = true;
      }
    } else if (notification is ScrollEndNotification) {
      _isScrolling = false;
    } else if (notification is UserScrollNotification && notification.direction == ScrollDirection.idle) {
      _isScrolling = false;
    }

    _syncTimers();
    if (notification is ScrollEndNotification ||
        notification is UserScrollNotification && notification.direction == ScrollDirection.idle) {
      _maybeFinish();
    }
    return false;
  }

  bool _handleMetricsNotification(ScrollMetricsNotification notification) {
    if (notification.depth != 0) return false;
    _updateMetrics(notification.metrics);
    _syncTimers();
    return false;
  }

  void _updateMetrics(ScrollMetrics metrics) {
    final wasAtBottom = _atBottom;
    _metricsKnown = true;
    _contentFits = metrics.maxScrollExtent <= 0;
    _atBottom = metrics.extentAfter <= _bottomTolerance;

    if (!_atBottom || wasAtBottom && !_contentFits && !_hasGenuineUserScroll) {
      _resetBottomIdle();
    }
  }

  @override
  Widget build(BuildContext context) {
    // Register inherited dependencies for route, tab, keyboard, and lifecycle
    // changes. These values are also read by the async validator.
    _tickerIsEnabled = TickerMode.valuesOf(context).enabled;
    _updateRouteEligibility();
    _syncTimers();
    _scheduleEngagementCheck();

    return NotificationListener<ScrollMetricsNotification>(
      onNotification: _handleMetricsNotification,
      child: NotificationListener<ScrollNotification>(
        onNotification: _handleScrollNotification,
        child: widget.child,
      ),
    );
  }
}
