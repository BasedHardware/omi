part of 'transcript.dart';

extension _TranscriptPlaybackScrolling on _TranscriptWidgetState {
  /// Scrolls the playback follow target into the top third. Triggered only on a
  /// new target id or a new explicit request — never on position ticks.
  void _followPlaybackTarget() {
    final targetId = widget.followTargetSegmentId;
    if (!widget.followCurrentSegment || targetId == null) return;
    if (targetId == _lastFollowTargetId && widget.playbackFollowRequest == _lastFollowRequest) return;
    _lastFollowTargetId = targetId;
    _lastFollowRequest = widget.playbackFollowRequest;
    _locateSegment(targetId, alignment: 1 / 3);
  }

  bool _onUserScroll(UserScrollNotification notification) {
    if (notification.direction != ScrollDirection.idle) {
      // User-directed motion (drag or fling momentum) outranks any follow or
      // pending anchor restore.
      _pendingAnchorRestore = false;
      _isUserScrolling = true;
      _userHasScrolled = true;
      _readerDragTakenOverByNative = true;
      _readerDragRecovered = false;
      _interruptAutoScroll();
      _noteUserGesture();
      _captureCurrentPosition();
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _isUserScrolling) _reportTopVisibleSegment();
      });
    } else if (_isUserScrolling && !_isRestoringAnchor && !_pendingAnchorRestore && !_readerDragRecovered) {
      _captureCurrentPosition();
      _isUserScrolling = false;
      _userGestureEnded();
    }
    return false;
  }

  bool _onScrollStart(ScrollStartNotification notification) {
    if (notification.depth != 0 || notification.dragDetails == null) return false;

    // Record intent on the first pixel of a pointer drag, before any live
    // follow can re-grab the scrollable.
    _pendingAnchorRestore = false;
    _isUserScrolling = true;
    _userHasScrolled = true;
    _readerDragTakenOverByNative = true;
    _readerDragRecovered = false;
    _interruptAutoScroll();
    _noteUserGesture();
    return false;
  }

  bool _onScrollUpdate(ScrollUpdateNotification notification) {
    if (notification.depth != 0) return false;
    if (notification.dragDetails == null) {
      // Ballistic momentum carries no drag details; while the reader still owns
      // the scroll it keeps moving the read point.
      if (_isUserScrolling && !_isAutoScrolling && !_isRestoringAnchor) {
        _reportTopVisibleSegment();
      }
      return false;
    }

    // A pointer drag always outranks follow and pending anchor restores.
    _pendingAnchorRestore = false;
    _isUserScrolling = true;
    _userHasScrolled = true;
    _readerDragTakenOverByNative = true;
    _readerDragRecovered = false;
    _interruptAutoScroll();
    _noteUserGesture();
    _captureCurrentPosition();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _isUserScrolling) _reportTopVisibleSegment();
    });
    return false;
  }

  bool _onScrollNotification(ScrollNotification notification) {
    if (notification is ScrollStartNotification) return _onScrollStart(notification);
    if (notification is ScrollUpdateNotification) return _onScrollUpdate(notification);
    if (notification is UserScrollNotification) return _onUserScroll(notification);
    return false;
  }

  bool _onScrollMetrics(ScrollMetricsNotification notification) {
    if (!widget.followLatest || _isAutoScrolling || _isUserScrolling || _userInterruptedAutoScroll) return false;
    final shouldFollow = !_userHasScrolled;
    if (shouldFollow && notification.metrics.extentAfter > 0.5) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _scrollToBottomGently(animated: false);
      });
    }
    return false;
  }

  /// Direction toward [segmentIndex] measured from the rows the list has
  /// actually built: -1 up, +1 down, 0 once the target is inside the built
  /// range. No height estimate is involved.
  int _locateDirection(int segmentIndex) {
    var minBuilt = widget.segments.length;
    var maxBuilt = -1;
    for (var i = 0; i < widget.segments.length; i++) {
      if (_segmentKeys[widget.segments[i].id]?.currentContext != null) {
        if (i < minBuilt) minBuilt = i;
        if (i > maxBuilt) maxBuilt = i;
      }
    }
    if (segmentIndex < minBuilt) return -1;
    if (segmentIndex > maxBuilt) return 1;
    return 0;
  }

  /// Scrolls [segmentId] so its row's leading edge sits [alignment] of the way
  /// down the viewport (1/3 keeps the current line near the top third).
  ///
  /// Pages one viewport at a time until the row is built — a measured
  /// continuation, not an estimate — then lands exactly. A reader gesture or a
  /// newer locate bumps [_locateGeneration] and stops the loop on the next
  /// frame boundary, so a locate can never re-grab a user drag.
  Future<void> _locateSegment(String segmentId, {required double alignment}) async {
    final generation = ++_locateGeneration;
    final index = widget.segments.indexWhere((segment) => segment.id == segmentId);
    if (index < 0) return;
    _isAutoScrolling = true;
    try {
      while (_segmentKeys[segmentId]?.currentContext == null) {
        if (!mounted || generation != _locateGeneration || !_scrollController.hasClients) return;
        final direction = _locateDirection(index);
        if (direction == 0) break;
        final position = _scrollController.position;
        final target = (position.pixels + direction * position.viewportDimension * 0.9).clamp(
          position.minScrollExtent,
          position.maxScrollExtent,
        );
        // At a stable edge with nothing left to reveal: stop rather than
        // jumping in place forever.
        if ((target - position.pixels).abs() < 0.5) return;
        _scrollController.jumpTo(target);
        await WidgetsBinding.instance.endOfFrame;
      }
      if (!mounted || generation != _locateGeneration || !_scrollController.hasClients) return;
      final renderObject = _segmentKeys[segmentId]?.currentContext?.findRenderObject();
      if (renderObject is! RenderBox) return;
      final viewport = RenderAbstractViewport.of(renderObject);
      final position = _scrollController.position;
      final target = (viewport.getOffsetToReveal(renderObject, 0).offset - position.viewportDimension * alignment)
          .clamp(position.minScrollExtent, position.maxScrollExtent);
      await _scrollController.animateTo(
        target,
        duration: const Duration(milliseconds: 400),
        curve: Curves.easeInOutCubic,
      );
    } finally {
      if (generation == _locateGeneration) _isAutoScrolling = false;
    }
  }

  /// The reader's intent: called once per drag, and again with the top
  /// visible segment as it changes. UserScroll/ScrollUpdate carry dragDetails
  /// only for real gestures, so programmatic scrolls never reach this.
  void _noteUserGesture() {
    _locateGeneration++;
    if (_userGestureNotified) return;
    _userGestureNotified = true;
    // Reset the top-segment dedupe once per gesture: repeated drag updates
    // must not re-report the same top segment as a fresh reader move.
    _lastReportedTopSegment = null;
    widget.onUserScroll?.call();
  }

  void _userGestureEnded() {
    _userGestureNotified = false;
    _reportTopVisibleSegment();
  }

  /// The topmost partially-visible segment — the smallest top that still
  /// intersects the viewport. Heading, leading items and the spacing rows are
  /// not segments; the last line at the viewport's bottom edge still counts.
  void _reportTopVisibleSegment() {
    final onTop = widget.onTopVisibleSegmentChanged;
    if (onTop == null || !_scrollController.hasClients) return;
    TranscriptSegment? topSegment;
    var closestTop = double.infinity;
    final currentScroll = _scrollController.offset;
    for (final segment in widget.segments) {
      final renderObject = _segmentKeys[segment.id]?.currentContext?.findRenderObject();
      if (renderObject is! RenderBox) continue;
      final viewport = RenderAbstractViewport.of(renderObject);
      final top = viewport.getOffsetToReveal(renderObject, 0).offset - currentScroll;
      final bottom = top + renderObject.size.height;
      if (bottom > 0 && top < _scrollController.position.viewportDimension && top < closestTop) {
        closestTop = top;
        topSegment = segment;
      }
    }
    if (topSegment != null && !identical(topSegment, _lastReportedTopSegment)) {
      _lastReportedTopSegment = topSegment;
      onTop(topSegment);
    }
  }
}
