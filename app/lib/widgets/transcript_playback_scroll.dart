part of 'transcript.dart';

/// The reading line, this share of the way down the transcript: following keeps the playing line
/// there, and a paused reader's scroll makes the line there the play point.
const double _readingLineFraction = 1 / 3;

extension _TranscriptPlaybackScrolling on _TranscriptWidgetState {
  /// Scrolls the playback follow target to the reading line. Triggered only on a
  /// new target id or a new explicit request — never on position ticks.
  void _followPlaybackTarget() {
    final targetId = widget.followTargetSegmentId;
    if (!widget.followCurrentSegment || targetId == null) return;
    if (targetId == _lastFollowTargetId && widget.playbackFollowRequest == _lastFollowRequest) return;
    _lastFollowTargetId = targetId;
    _lastFollowRequest = widget.playbackFollowRequest;
    _locateSegment(targetId, alignment: _readingLineFraction);
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
        if (mounted && _isUserScrolling) _reportReadingSegment();
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
        _reportReadingSegment();
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
      if (mounted && _isUserScrolling) _reportReadingSegment();
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
  /// down the viewport ([_readingLineFraction] puts it on the reading line).
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

  /// The reader's intent: called once per drag, and again with the reading
  /// segment as it changes. UserScroll/ScrollUpdate carry dragDetails
  /// only for real gestures, so programmatic scrolls never reach this.
  void _noteUserGesture() {
    _locateGeneration++;
    if (_userGestureNotified) return;
    _userGestureNotified = true;
    // Reset the reading-segment dedupe once per gesture: repeated drag updates
    // must not re-report the same segment as a fresh reader move.
    _lastReportedReadingSegment = null;
    widget.onUserScroll?.call();
  }

  void _userGestureEnded() {
    _userGestureNotified = false;
    _reportReadingSegment();
  }

  /// The segment at the reading line, [_readingLineFraction] of the way down
  /// the viewport: the last line whose words start at or above it, so a paused
  /// reader's play point is where following keeps the playing line. The
  /// reading line is never lower than the distance scrolled, so at the top of
  /// the list it is the top edge and the first line is the play point; with
  /// nothing at or above it, the topmost visible line counts. Heading, leading
  /// items and the spacing rows are not segments.
  void _reportReadingSegment() {
    final onReading = widget.onReadingSegmentChanged;
    if (onReading == null || !_scrollController.hasClients) return;
    final position = _scrollController.position;
    final readingLine = min(
      position.viewportDimension * _readingLineFraction,
      position.pixels - position.minScrollExtent,
    );
    TranscriptSegment? atLine;
    var atLineTop = double.negativeInfinity;
    TranscriptSegment? topVisible;
    var topVisibleTop = double.infinity;
    for (final segment in widget.segments) {
      final renderObject = _segmentKeys[segment.id]?.currentContext?.findRenderObject();
      if (renderObject is! RenderBox) continue;
      final viewport = RenderAbstractViewport.of(renderObject);
      final top = viewport.getOffsetToReveal(renderObject, 0).offset - position.pixels;
      final bottom = top + renderObject.size.height;
      if (top <= readingLine && top > atLineTop) {
        atLine = segment;
        atLineTop = top;
      }
      if (bottom >= 0 && top < position.viewportDimension && top < topVisibleTop) {
        topVisible = segment;
        topVisibleTop = top;
      }
    }
    final segment = atLine ?? topVisible;
    if (segment != null && !identical(segment, _lastReportedReadingSegment)) {
      _lastReportedReadingSegment = segment;
      onReading(segment);
    }
  }
}
