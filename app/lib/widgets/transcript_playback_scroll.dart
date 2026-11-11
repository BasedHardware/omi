part of 'transcript.dart';

extension _TranscriptPlaybackScrolling on _TranscriptWidgetState {
  void _captureCurrentPosition({String? layoutIdentity}) {
    if (!_scrollController.hasClients) return;

    final currentScroll = _scrollController.offset;
    final isAtBottom = _scrollController.position.maxScrollExtent - currentScroll <= 24;
    _userHasScrolled = !isAtBottom;
    if (isAtBottom && !_isUserScrolling) {
      // Settled at the live edge: resume follow. Do not clear this during an
      // active drag — a reader who has only moved a few pixels must still win.
      _userInterruptedAutoScroll = false;
    }
    final scrollState = widget.scrollState;
    if (scrollState != null) {
      String? anchorId;
      var anchorIndex = 0;
      var anchorViewportOffset = 0.0;
      if (!isAtBottom) {
        final visible = _topVisibleSegment();
        if (visible != null) {
          anchorIndex = visible.index;
          anchorId = widget.segments[anchorIndex].id;
          anchorViewportOffset = visible.top;
        }
      }
      scrollState.update(
        offset: currentScroll,
        isAtBottom: isAtBottom,
        anchorSegmentId: anchorId,
        anchorSegmentIndex: anchorIndex,
        anchorViewportOffset: anchorViewportOffset,
        layoutIdentity: layoutIdentity ?? widget.layoutIdentity,
      );
    }
    _setIsAtBottom(isAtBottom);
  }

  // Reveal coordinates remain valid even when a notification arrives during
  // layout, before the viewport has updated its slivers' paint transforms.
  double _viewportTopOf(RenderBox row) {
    widget.onScrollRevealProbe?.call();
    final viewport = RenderAbstractViewport.of(row);
    return viewport.getOffsetToReveal(row, 0).offset -
        _scrollController.offset +
        (_endAnchored ? _scrollController.position.viewportDimension * (viewport as RenderViewport).anchor : 0);
  }

  List<RenderSliverMultiBoxAdaptor> _listSlivers() {
    // The scrollable owns these slivers for its mounted lifetime. Discover
    // them once, rather than walking the render tree on every notification.
    // A mode change replaces the scrollable and detaches the old slivers.
    if (_cachedListSlivers.isNotEmpty && _cachedListSlivers.every((sliver) => sliver.attached)) {
      return _cachedListSlivers;
    }
    _cachedListSlivers.clear();
    final root = _listKey.currentContext?.findRenderObject();
    void visit(RenderObject object) {
      widget.onScrollGeometryProbe?.call();
      if (object is RenderSliverMultiBoxAdaptor) {
        _cachedListSlivers.add(object);
      } else {
        object.visitChildren(visit);
      }
    }

    if (root != null) visit(root);
    return _cachedListSlivers;
  }

  /// Direct children in the slivers' layout/cache window, never kept-alive
  /// offscreen rows. Mapping an index and reading its layout offset both take
  /// constant work, independent of transcript length or row depth.
  Iterable<({int index, RenderBox row})> _builtSegmentRows() sync* {
    final slivers = _listSlivers();
    for (var sliverIndex = 0; sliverIndex < slivers.length; sliverIndex++) {
      final rows = slivers[sliverIndex];
      var child = rows.firstChild;
      while (child != null) {
        var itemIndex = (child.parentData! as SliverMultiBoxAdaptorParentData).index;
        if (itemIndex != null) {
          if (_endAnchored) {
            itemIndex = sliverIndex == 0 ? _liveBoundary - 1 - itemIndex : _liveBoundary + itemIndex;
          }
          final segmentIndex = itemIndex - widget.leadingItems.length - 1;
          if (segmentIndex >= 0 && segmentIndex < widget.segments.length) {
            yield (index: segmentIndex, row: child);
          }
        }
        child = rows.childAfter(child);
      }
    }
  }

  Iterable<int> _builtSegmentIndices() => _builtSegmentRows().map((entry) => entry.index);

  ({int index, double top})? _topVisibleSegment() {
    ({int index, double top})? visible;
    final viewportHeight = _scrollController.position.viewportDimension;
    // Resolve the sliver origin once. Every remaining row position is just
    // arithmetic on SliverList's existing layout offsets, including the
    // upward-growing live history. No per-row key lookup or reveal walk.
    RenderObject? previousSliver;
    var originTop = 0.0;
    var originOffset = 0.0;
    var originHeight = 0.0;
    var reverse = false;
    for (final entry in _builtSegmentRows()) {
      widget.onScrollGeometryProbe?.call();
      final row = entry.row;
      final parentData = row.parentData! as SliverMultiBoxAdaptorParentData;
      if (!identical(row.parent, previousSliver)) {
        previousSliver = row.parent;
        originTop = _viewportTopOf(row);
        originOffset = parentData.layoutOffset!;
        originHeight = row.size.height;
        reverse = _endAnchored && identical(previousSliver, _cachedListSlivers.first);
      }
      final delta = parentData.layoutOffset! - originOffset;
      final rowTop = reverse ? originTop - delta - row.size.height + originHeight : originTop + delta;
      // The segment key is inside its inter-row spacing. Preserve the same
      // intersection rule as the content box used by search and playback.
      final top = rowTop + (widget.separator && entry.index > 0 ? 4 : 0);
      final bottom = rowTop + row.size.height;
      if (bottom > 0 && top < viewportHeight && (visible == null || top < visible.top)) {
        visible = (index: entry.index, top: top);
      }
    }
    return visible;
  }

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
    for (final i in _builtSegmentIndices()) {
      if (i < minBuilt) minBuilt = i;
      if (i > maxBuilt) maxBuilt = i;
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
      final position = _scrollController.position;
      final target = (position.pixels + _viewportTopOf(renderObject) - position.viewportDimension * alignment)
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
    final visible = _topVisibleSegment();
    final topSegment = visible == null ? null : widget.segments[visible.index];
    if (topSegment != null && !identical(topSegment, _lastReportedTopSegment)) {
      _lastReportedTopSegment = topSegment;
      onTop(topSegment);
    }
  }
}
