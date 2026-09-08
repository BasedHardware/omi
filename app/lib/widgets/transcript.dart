import 'dart:convert';
import 'dart:math';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show RenderAbstractViewport, RenderBox, ScrollDirection;
import 'package:flutter/services.dart';
import 'package:flutter/gestures.dart' show kTouchSlop, PointerDownEvent, PointerMoveEvent;
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/utils/constants.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

// Use speaker colors from person.dart for bubble colors
final List<Color> _speakerColors = speakerColors;

typedef TranscriptSegmentBuilder = Widget Function(BuildContext context, TranscriptSegment segment, int index);

class TranscriptWidget extends StatefulWidget {
  final List<TranscriptSegment> segments;
  final bool horizontalMargin;
  final bool topMargin;
  final bool separator;
  final bool canDisplaySeconds;
  final bool isConversationDetail;
  final double bottomMargin;
  final Function(String, int)? editSegment;
  final Map<String, SpeakerLabelSuggestionEvent> suggestions;
  final List<String> taggingSegmentIds;
  final Function(SpeakerLabelSuggestionEvent)? onAcceptSuggestion;
  final String searchQuery;
  final int currentResultIndex;
  final Function(ScrollController)? onScrollControllerReady;
  final VoidCallback? onTapWhenSearchEmpty;
  final Function(TranscriptSegment)? onSegmentTap;
  final Function(int segmentIndex)? onEditSegmentText;
  final bool followLatest;
  final TranscriptScrollState? scrollState;
  final double jumpToLatestButtonBottom;
  final int contentVersion;
  final String layoutIdentity;
  final List<Widget> leadingItems;
  final List<String> leadingItemIds;
  final TranscriptSegmentBuilder? segmentBuilder;

  const TranscriptWidget({
    super.key,
    required this.segments,
    this.horizontalMargin = true,
    this.topMargin = true,
    this.separator = true,
    this.canDisplaySeconds = true,
    this.isConversationDetail = false,
    this.bottomMargin = 200,
    this.editSegment,
    this.suggestions = const {},
    this.taggingSegmentIds = const [],
    this.onAcceptSuggestion,
    this.searchQuery = '',
    this.currentResultIndex = -1,
    this.onScrollControllerReady,
    this.onTapWhenSearchEmpty,
    this.onSegmentTap,
    this.onEditSegmentText,
    this.followLatest = false,
    this.scrollState,
    this.jumpToLatestButtonBottom = 16,
    this.contentVersion = 0,
    this.layoutIdentity = 'transcript',
    this.leadingItems = const [],
    this.leadingItemIds = const [],
    this.segmentBuilder,
  }) : assert(leadingItems.length == leadingItemIds.length);

  @override
  State<TranscriptWidget> createState() => _TranscriptWidgetState();
}

class TranscriptScrollState {
  bool hasPosition = false;
  double offset = 0;
  bool isAtBottom = true;
  String? anchorSegmentId;
  int anchorSegmentIndex = 0;
  double anchorViewportOffset = 0;
  String? layoutIdentity;

  void update({
    required double offset,
    required bool isAtBottom,
    String? anchorSegmentId,
    int? anchorSegmentIndex,
    double? anchorViewportOffset,
    String? layoutIdentity,
  }) {
    hasPosition = true;
    this.offset = offset;
    this.isAtBottom = isAtBottom;
    if (anchorSegmentId != null) this.anchorSegmentId = anchorSegmentId;
    if (anchorSegmentIndex != null) this.anchorSegmentIndex = anchorSegmentIndex;
    if (anchorViewportOffset != null) this.anchorViewportOffset = anchorViewportOffset;
    if (layoutIdentity != null) this.layoutIdentity = layoutIdentity;
  }
}

/// Owns live-transcript scroll intent for one mounted page.
///
/// A new page gets a fresh store and therefore starts at the live edge. The
/// same page can still reuse its position when its transcript switches between
/// the text-only and photo timeline layouts.
class TranscriptScrollStateStore {
  String? _sessionId;
  TranscriptScrollState _state = TranscriptScrollState();

  TranscriptScrollState forSession(String sessionId) {
    if (_sessionId != sessionId) {
      _sessionId = sessionId;
      _state = TranscriptScrollState();
    }
    return _state;
  }
}

class _TranscriptWidgetState extends State<TranscriptWidget> {
  // Cache for person data to avoid repeated lookups
  final Map<String?, Person?> _personCache = {};
  // Cache for decoded text to avoid repeated decoding
  final Map<String, String> _decodedTextCache = {};

  // ScrollController to enable proper scrolling
  late final ScrollController _scrollController;

  // Auto-scroll state management
  bool _userHasScrolled = false;
  bool _isAutoScrolling = false;
  bool _userInterruptedAutoScroll = false;
  bool _isUserScrolling = false;
  bool _isRestoringAnchor = false;
  bool _pendingAnchorRestore = false;
  bool _isAtBottom = true;
  bool _followAgain = false;
  Future<void>? _activeFollow;
  // Reader drag tracking: while a programmatic follow owns the scrollable,
  // the scrollable may ignore pointers or replace its recognizers, orphaning
  // a pending drag. The ancestor Listener below recovers that gesture.
  int? _readerDragPointer;
  Offset? _lastReaderPointerPosition;
  double _readerDragTravel = 0;
  bool _readerDragTakenOverByNative = false;
  bool _readerDragRecovered = false;

  // Search result tracking
  final Map<String, GlobalKey> _segmentKeys = {};
  final List<GlobalKey> _matchKeys = [];
  int _previousSearchResultIndex = -1;

  Color _getSpeakerBubbleColor(bool isUser, int speakerId, Person? person) {
    if (isUser) {
      return const Color(0xFF8B5CF6).withValues(alpha: 0.8);
    }
    final colorIndex = (person?.colorIdx ?? speakerId) % _speakerColors.length;
    return _speakerColors[colorIndex].withValues(alpha: 0.8);
  }

  Color _getSpeakerAvatarColor(bool isUser, int speakerId, Person? person) {
    if (isUser) {
      return const Color(0xFF8B5CF6).withValues(alpha: 0.3);
    }
    if (speakerId == omiSpeakerId) {
      return Colors.purple.withValues(alpha: 0.3);
    }
    final colorIndex = (person?.colorIdx ?? speakerId) % _speakerColors.length;
    return _speakerColors[colorIndex].withValues(alpha: 0.3);
  }

  Widget _getSpeakerAvatar(int speakerId, bool isUser, Person? person) {
    if (speakerId == omiSpeakerId) {
      return Image.asset(Assets.images.herologo.path, height: 16, width: 16);
    }
    if (isUser) {
      return Image.asset(Assets.images.speaker0Icon.path, width: 24, height: 24);
    }
    // Always modulo by speakerImagePath.length to prevent index out of bounds
    final imageIndex =
        person != null ? person.colorIdx! % speakerImagePath.length : speakerId % speakerImagePath.length;
    return Image.asset(speakerImagePath[imageIndex], width: 24, height: 24);
  }

  @override
  void initState() {
    super.initState();
    final savedState = widget.scrollState;
    final shouldRestorePosition = savedState?.hasPosition == true && !savedState!.isAtBottom;
    final canUseRawOffset = savedState?.layoutIdentity == null || savedState?.layoutIdentity == widget.layoutIdentity;
    _pendingAnchorRestore = shouldRestorePosition && !canUseRawOffset;
    _scrollController = ScrollController(
      initialScrollOffset: shouldRestorePosition && canUseRawOffset ? savedState.offset : 0,
    );
    _userHasScrolled = shouldRestorePosition;
    _isAtBottom = !shouldRestorePosition;
    _syncSegmentKeys();
    _rebuildMatchKeys();

    // Add scroll listener to detect manual scrolling
    _scrollController.addListener(_onScroll);

    // Notify parent about scroll controller
    widget.onScrollControllerReady?.call(_scrollController);

    if ((widget.segments.isNotEmpty || widget.leadingItems.isNotEmpty) &&
        (widget.isConversationDetail || widget.followLatest)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        if (widget.followLatest && _userHasScrolled) {
          if (canUseRawOffset) {
            _setIsAtBottom(false);
          } else {
            _restoreAnchor();
          }
        } else {
          _scrollToBottomGently(animated: widget.isConversationDetail);
        }
      });
    }
  }

  void _syncSegmentKeys() {
    final currentIds = widget.segments.map((segment) => segment.id).toSet();
    _segmentKeys.removeWhere((id, _) => !currentIds.contains(id));
    for (final segment in widget.segments) {
      _segmentKeys.putIfAbsent(segment.id, GlobalKey.new);
    }
  }

  void _rebuildMatchKeys() {
    _matchKeys.clear();
    if (widget.searchQuery.isEmpty) return;

    final searchQuery = widget.searchQuery.toLowerCase();

    for (var segment in widget.segments) {
      final text = _getDecodedText(segment.text).toLowerCase();
      final matches = RegExp(RegExp.escape(searchQuery), caseSensitive: false).allMatches(text);
      for (final _ in matches) {
        _matchKeys.add(GlobalKey());
      }
    }
  }

  @override
  void didUpdateWidget(TranscriptWidget oldWidget) {
    super.didUpdateWidget(oldWidget);

    final contentChanged = widget.contentVersion != oldWidget.contentVersion ||
        widget.segments.length != oldWidget.segments.length ||
        widget.leadingItems.length != oldWidget.leadingItems.length ||
        widget.layoutIdentity != oldWidget.layoutIdentity;
    final shouldFollow = !_userHasScrolled;

    if (contentChanged && !shouldFollow) _pendingAnchorRestore = true;
    _syncSegmentKeys();

    if (widget.searchQuery != oldWidget.searchQuery) {
      _rebuildMatchKeys();
      _previousSearchResultIndex = -1;

      if (widget.searchQuery.isNotEmpty && widget.currentResultIndex >= 0) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          _scrollToSearchResult();
        });
      }
    }

    if (contentChanged) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        if (shouldFollow) {
          _scrollToBottomGently();
        } else {
          _restoreAnchor();
        }
      });
    }

    // Handle search result navigation
    if (widget.currentResultIndex != _previousSearchResultIndex &&
        widget.currentResultIndex >= 0 &&
        widget.searchQuery.isNotEmpty) {
      _previousSearchResultIndex = widget.currentResultIndex;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _scrollToSearchResult();
      });
    }
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (!_scrollController.hasClients) return;

    final currentScroll = _scrollController.offset;
    final distanceFromBottom = _scrollController.position.maxScrollExtent - currentScroll;
    final isAtBottom = distanceFromBottom <= 24;
    if (!_isAutoScrolling && !_isRestoringAnchor && !_pendingAnchorRestore) {
      // Record the reader's intent on the first pixel of a drag. A live update
      // can arrive before Flutter emits the corresponding idle notification.
      final wasUserHasScrolled = _userHasScrolled;
      _userHasScrolled = !isAtBottom;
      if (isAtBottom && wasUserHasScrolled) {
        // The reader is demonstrably back at the live edge: a stale interrupt
        // from an earlier gesture must not keep blocking follow.
        _userInterruptedAutoScroll = false;
        widget.scrollState?.update(offset: currentScroll, isAtBottom: true, layoutIdentity: widget.layoutIdentity);
      }
    }
    _setIsAtBottom(isAtBottom);
  }

  /// Cancels any in-flight follow on behalf of a reader gesture.
  ///
  /// Setting the flags alone is not enough: the running `animateTo` keeps
  /// driving the Scrollable and can yank the reader back to the live edge.
  /// Stopping at the current offset kills the driven activity immediately, and
  /// clearing [_activeFollow] lets a later follow (e.g. the jump button) start
  /// fresh instead of awaiting this cancelled one.
  void _interruptAutoScroll() {
    _userInterruptedAutoScroll = true;
    _followAgain = false;
    _activeFollow = null;
    if (_isAutoScrolling && _scrollController.hasClients) {
      _scrollController.jumpTo(_scrollController.offset);
    }
    _isAutoScrolling = false;
  }

  void _onReaderPointerDown(PointerDownEvent event) {
    if (_readerDragPointer != null) return;
    _readerDragPointer = event.pointer;
    _lastReaderPointerPosition = event.position;
    _readerDragTravel = 0;
    _readerDragTakenOverByNative = false;
    _readerDragRecovered = false;
  }

  void _onReaderPointerMove(PointerMoveEvent event) {
    if (_readerDragPointer != event.pointer) return;
    final last = _lastReaderPointerPosition;
    _lastReaderPointerPosition = event.position;
    if (last == null || !_scrollController.hasClients) return;

    final dy = event.position.dy - last.dy;
    if (_readerDragTakenOverByNative) return;

    if (_readerDragRecovered) {
      // The scrollable never saw this pointer's down event, so it cannot
      // drive the gesture natively; carry the drag manually.
      _driveReaderDrag(dy);
      return;
    }

    final programmaticScrollActive = _isAutoScrolling || _isRestoringAnchor || _pendingAnchorRestore;
    _readerDragTravel += dy.abs();
    if (!programmaticScrollActive || _readerDragTravel <= kTouchSlop) return;

    // A reader drag against a running programmatic scroll must interrupt it:
    // while a driven activity owns the scrollable this gesture may never be
    // delivered as a native drag, and the follow would yank the reader back
    // to the live edge and re-pin.
    _pendingAnchorRestore = false;
    _isUserScrolling = true;
    _userHasScrolled = true;
    _readerDragRecovered = true;
    _interruptAutoScroll();
    _driveReaderDrag(dy);
  }

  void _driveReaderDrag(double dy) {
    if (!_scrollController.hasClients) return;
    final position = _scrollController.position;
    _scrollController.jumpTo((_scrollController.offset - dy).clamp(position.minScrollExtent, position.maxScrollExtent));
  }

  void _endReaderDrag(int pointer) {
    if (_readerDragPointer != pointer) return;
    final recovered = _readerDragRecovered && !_readerDragTakenOverByNative;
    _readerDragPointer = null;
    _lastReaderPointerPosition = null;
    _readerDragTravel = 0;
    _readerDragTakenOverByNative = false;
    _readerDragRecovered = false;
    if (recovered && _isUserScrolling && !_isAutoScrolling && !_isRestoringAnchor) {
      _captureCurrentPosition();
      _isUserScrolling = false;
    }
  }

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
        var closestTop = double.infinity;
        for (var index = 0; index < widget.segments.length; index++) {
          final segment = widget.segments[index];
          final renderObject = _segmentKeys[segment.id]?.currentContext?.findRenderObject();
          if (renderObject is! RenderBox) continue;
          final viewport = RenderAbstractViewport.of(renderObject);
          final top = viewport.getOffsetToReveal(renderObject, 0).offset - currentScroll;
          final bottom = top + renderObject.size.height;
          if (bottom > 0 && top < _scrollController.position.viewportDimension && top < closestTop) {
            closestTop = top;
            anchorId = segment.id;
            anchorIndex = index;
            anchorViewportOffset = top;
          }
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

  Future<void> _restoreAnchor() async {
    if (!_scrollController.hasClients) return;
    final scrollState = widget.scrollState;
    if (_isUserScrolling) {
      // The reader's active gesture owns the position; it re-anchors on its
      // own when the gesture goes idle.
      _pendingAnchorRestore = false;
      return;
    }
    if (scrollState == null || scrollState.isAtBottom || widget.segments.isEmpty) {
      _pendingAnchorRestore = false;
      _captureCurrentPosition();
      return;
    }

    var anchorIndex = widget.segments.indexWhere((segment) => segment.id == scrollState.anchorSegmentId);
    if (anchorIndex < 0) {
      anchorIndex = scrollState.anchorSegmentIndex.clamp(0, widget.segments.length - 1).toInt();
    }
    final anchorId = widget.segments[anchorIndex].id;

    _isAutoScrolling = true;
    _isRestoringAnchor = true;
    try {
      for (var attempt = 0; attempt < 20; attempt++) {
        if (!mounted || !_scrollController.hasClients || _isUserScrolling) return;
        final anchorContext = _segmentKeys[anchorId]?.currentContext;
        final anchor = anchorContext?.findRenderObject();
        if (anchor is RenderBox) {
          final viewport = RenderAbstractViewport.of(anchor);
          final anchorViewportOffset = viewport.getOffsetToReveal(anchor, 0).offset - _scrollController.offset;
          final correction = anchorViewportOffset - scrollState.anchorViewportOffset;
          if (correction.abs() <= 0.5) break;
          final target = (_scrollController.offset + correction).clamp(
            _scrollController.position.minScrollExtent,
            _scrollController.position.maxScrollExtent,
          );
          _scrollController.jumpTo(target);
          await WidgetsBinding.instance.endOfFrame;
          continue;
        }

        final itemIndex = widget.leadingItems.length + anchorIndex + 1;
        final itemCount = widget.leadingItems.length + widget.segments.length + 2;
        final fraction = itemIndex / max(1, itemCount - 1);
        _scrollController.jumpTo(_scrollController.position.maxScrollExtent * fraction);
        await WidgetsBinding.instance.endOfFrame;
      }
    } finally {
      _pendingAnchorRestore = false;
      _isRestoringAnchor = false;
      _isAutoScrolling = false;
    }

    if (!mounted || !_scrollController.hasClients) return;
    _userHasScrolled = true;
    scrollState.update(
      offset: _scrollController.offset,
      isAtBottom: false,
      anchorSegmentId: anchorId,
      anchorSegmentIndex: anchorIndex,
      anchorViewportOffset: scrollState.anchorViewportOffset,
      layoutIdentity: widget.layoutIdentity,
    );
    _setIsAtBottom(false);
  }

  void _setIsAtBottom(bool value) {
    if (_isAtBottom == value || !mounted) return;
    setState(() => _isAtBottom = value);
  }

  Future<void> _runFollowToBottom({required bool animated}) async {
    _isAutoScrolling = true;
    _userInterruptedAutoScroll = false;
    var firstPass = true;
    try {
      do {
        _followAgain = false;

        // ListView.builder refines maxScrollExtent as previously lazy rows are
        // laid out. Follow that moving edge until both layout and queued content
        // updates settle.
        for (var attempt = 0; attempt < 20; attempt++) {
          final target = _scrollController.position.maxScrollExtent;
          if (animated) {
            await _scrollController.animateTo(
              target,
              duration: Duration(milliseconds: firstPass ? 500 : 100),
              curve: Curves.easeInOut,
            );
          } else {
            _scrollController.jumpTo(target);
          }
          firstPass = false;

          if (_userInterruptedAutoScroll) return;

          await WidgetsBinding.instance.endOfFrame;
          if (!mounted || !_scrollController.hasClients || _userInterruptedAutoScroll) return;

          final remaining = _scrollController.position.maxScrollExtent - _scrollController.offset;
          if (remaining.abs() <= 0.5) break;
        }
      } while (_followAgain && !_userInterruptedAutoScroll);

      if (!mounted || !_scrollController.hasClients || _userInterruptedAutoScroll) return;
      final maxExtent = _scrollController.position.maxScrollExtent;
      if ((maxExtent - _scrollController.offset).abs() > 0.5) {
        _scrollController.jumpTo(maxExtent);
      }
      // Re-pin only when the follow truly finished at the live edge and the
      // reader never took the gesture back.
      if (!_userInterruptedAutoScroll &&
          (_scrollController.position.maxScrollExtent - _scrollController.offset).abs() <= 0.5) {
        _userHasScrolled = false;
        widget.scrollState?.update(offset: maxExtent, isAtBottom: true, layoutIdentity: widget.layoutIdentity);
        _setIsAtBottom(true);
      }
    } finally {
      _isAutoScrolling = false;
    }
  }

  Future<void> _scrollToBottomGently({bool animated = true, bool force = false}) {
    if (!_scrollController.hasClients) return Future.value();
    if (!force && widget.followLatest && (_userHasScrolled || _isUserScrolling || _userInterruptedAutoScroll)) {
      return Future.value();
    }
    _followAgain = true;
    final activeFollow = _activeFollow;
    if (activeFollow != null) return activeFollow;

    late final Future<void> trackedFollow;
    trackedFollow = _runFollowToBottom(animated: animated).whenComplete(() {
      if (identical(_activeFollow, trackedFollow)) _activeFollow = null;
    });
    _activeFollow = trackedFollow;
    return trackedFollow;
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
      _captureCurrentPosition();
    } else if (_isUserScrolling && !_isRestoringAnchor && !_pendingAnchorRestore && !_readerDragRecovered) {
      _captureCurrentPosition();
      _isUserScrolling = false;
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
    return false;
  }

  bool _onScrollUpdate(ScrollUpdateNotification notification) {
    if (notification.depth != 0 || notification.dragDetails == null) return false;

    // A pointer drag always outranks follow and pending anchor restores.
    _pendingAnchorRestore = false;
    _isUserScrolling = true;
    _userHasScrolled = true;
    _readerDragTakenOverByNative = true;
    _readerDragRecovered = false;
    _interruptAutoScroll();
    _captureCurrentPosition();
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

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
  }

  void _scrollToSearchResult() {
    if (!_scrollController.hasClients) {
      return;
    }

    if (widget.searchQuery.isEmpty) {
      return;
    }

    if (widget.currentResultIndex < 0 || widget.currentResultIndex >= _matchKeys.length) {
      return;
    }

    final matchKey = _matchKeys[widget.currentResultIndex];
    final context = matchKey.currentContext;

    if (context != null) {
      _scrollToContext(context);
    } else {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        final retryContext = matchKey.currentContext;
        if (retryContext != null) {
          _scrollToContext(retryContext);
        } else {
          _scrollToSearchResultFallback();
        }
      });
    }
  }

  void _scrollToContext(BuildContext context) {
    _isAutoScrolling = true;
    Scrollable.ensureVisible(
      context,
      duration: const Duration(milliseconds: 400),
      curve: Curves.easeInOutCubic,
      alignment: 0.35,
    ).then((_) {
      _isAutoScrolling = false;
    });
  }

  void _scrollToSearchResultFallback() {
    final searchQuery = widget.searchQuery.toLowerCase();
    int currentMatchIndex = 0;
    int targetSegmentIndex = -1;

    for (int segmentIndex = 0; segmentIndex < widget.segments.length; segmentIndex++) {
      final text = _getDecodedText(widget.segments[segmentIndex].text).toLowerCase();
      final matches = RegExp(RegExp.escape(searchQuery), caseSensitive: false).allMatches(text);

      if (currentMatchIndex + matches.length > widget.currentResultIndex) {
        targetSegmentIndex = segmentIndex;
        break;
      }
      currentMatchIndex += matches.length;
    }

    if (targetSegmentIndex >= 0 && targetSegmentIndex < _segmentKeys.length) {
      final segmentKey = _segmentKeys[widget.segments[targetSegmentIndex].id];

      final segmentContext = segmentKey?.currentContext;
      if (segmentContext != null) {
        _scrollToContext(segmentContext);
        return;
      }

      const itemHeight = 80.0;
      final headerHeight = widget.topMargin ? 32.0 : 0.0;
      final targetOffset = headerHeight + (targetSegmentIndex * itemHeight);

      _isAutoScrolling = true;
      _scrollController
          .animateTo(
        targetOffset.clamp(0.0, _scrollController.position.maxScrollExtent),
        duration: const Duration(milliseconds: 400),
        curve: Curves.easeInOutCubic,
      )
          .then((_) {
        _isAutoScrolling = false;
      });
    }
  }

  String _getDecodedText(String text) {
    if (!_decodedTextCache.containsKey(text)) {
      _decodedTextCache[text] = tryDecodingText(text);
    }
    return _decodedTextCache[text]!;
  }

  // Create highlighted text spans
  List<InlineSpan> _highlightSearchMatchesWithKeys(String text, String searchQuery, int segmentIndex) {
    if (searchQuery.isEmpty) {
      return [TextSpan(text: text)];
    }

    final spans = <InlineSpan>[];
    final lowerText = text.toLowerCase();
    final lowerQuery = searchQuery.toLowerCase();

    int globalMatchIndex = 0;
    for (int i = 0; i < segmentIndex; i++) {
      final segmentText = _getDecodedText(widget.segments[i].text).toLowerCase();
      final matches = RegExp(RegExp.escape(lowerQuery), caseSensitive: false).allMatches(segmentText);
      globalMatchIndex += matches.length;
    }

    int start = 0;
    final matches = RegExp(RegExp.escape(lowerQuery), caseSensitive: false).allMatches(lowerText);

    for (final match in matches) {
      final matchStart = match.start;
      final matchEnd = match.end;

      if (matchStart > start) {
        spans.add(TextSpan(text: text.substring(start, matchStart)));
      }

      final currentGlobalIndex = globalMatchIndex;
      final isCurrentResult = currentGlobalIndex == widget.currentResultIndex;

      final matchKey = currentGlobalIndex < _matchKeys.length ? _matchKeys[currentGlobalIndex] : null;

      spans.add(
        WidgetSpan(
          child: Container(
            key: matchKey,
            decoration: BoxDecoration(
              color: isCurrentResult ? Colors.orange.withValues(alpha: 0.9) : Colors.deepPurple.withValues(alpha: 0.6),
              borderRadius: BorderRadius.circular(2),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 1),
            child: Text(
              text.substring(matchStart, matchEnd),
              style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
            ),
          ),
        ),
      );

      start = matchEnd;
      globalMatchIndex++;
    }

    if (start < text.length) {
      spans.add(TextSpan(text: text.substring(start)));
    }

    return spans;
  }

  Person? _getPersonById(String? personId) {
    if (personId == null) return null;
    if (!_personCache.containsKey(personId)) {
      _personCache[personId] = SharedPreferencesUtil().getPersonById(personId);
    }
    return _personCache[personId];
  }

  @override
  Widget build(BuildContext context) {
    final searchBarHeight = widget.searchQuery.isNotEmpty ? 100.0 : 0.0;
    final transcriptList = NotificationListener<ScrollMetricsNotification>(
      onNotification: _onScrollMetrics,
      child: NotificationListener<ScrollNotification>(
        onNotification: _onScrollNotification,
        child: Listener(
          onPointerDown: _onReaderPointerDown,
          onPointerMove: _onReaderPointerMove,
          onPointerUp: (event) => _endReaderDrag(event.pointer),
          onPointerCancel: (event) => _endReaderDrag(event.pointer),
          child: GestureDetector(
            behavior: HitTestBehavior.translucent,
            onTap: () {
              if (widget.searchQuery.isEmpty && widget.onTapWhenSearchEmpty != null) {
                widget.onTapWhenSearchEmpty!();
              }
            },
            child: ListView.builder(
              controller: _scrollController,
              padding: EdgeInsets.only(top: searchBarHeight),
              itemCount: widget.leadingItems.length + widget.segments.length + 2,
              findChildIndexCallback: _findChildIndex,
              itemBuilder: (context, idx) {
                if (idx == 0) {
                  return SizedBox(key: const ValueKey('transcript_header'), height: widget.topMargin ? 32 : 0);
                }

                final leadingIndex = idx - 1;
                if (leadingIndex < widget.leadingItems.length) {
                  return KeyedSubtree(
                    key: ValueKey('transcript-leading-${widget.leadingItemIds[leadingIndex]}'),
                    child: widget.leadingItems[leadingIndex],
                  );
                }

                final segmentIndex = idx - widget.leadingItems.length - 1;
                if (segmentIndex == widget.segments.length) {
                  return SizedBox(key: const ValueKey('transcript_bottom_spacing'), height: widget.bottomMargin + 120);
                }

                final segment = widget.segments[segmentIndex];
                final customSegment = widget.segmentBuilder?.call(context, segment, segmentIndex);
                Widget child = customSegment == null
                    ? _buildSegmentItem(segmentIndex)
                    : Container(key: _segmentKeys[segment.id], child: customSegment);
                if (widget.separator && segmentIndex > 0) {
                  child = Column(mainAxisSize: MainAxisSize.min, children: [const SizedBox(height: 4), child]);
                }
                return KeyedSubtree(key: ValueKey('transcript-segment-${segment.id}'), child: child);
              },
            ),
          ),
        ),
      ),
    );

    if (!widget.followLatest) return transcriptList;

    return Stack(
      children: [
        Positioned.fill(child: transcriptList),
        PositionedDirectional(
          end: 16,
          bottom: widget.jumpToLatestButtonBottom,
          child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 180),
            transitionBuilder: (child, animation) => FadeTransition(
              opacity: animation,
              child: ScaleTransition(scale: animation, child: child),
            ),
            child: _isAtBottom
                ? const SizedBox.shrink(key: ValueKey('transcript_jump_to_latest_hidden'))
                : Semantics(
                    button: true,
                    label: context.l10n.jumpToLatestMessage,
                    child: FloatingActionButton.small(
                      key: const ValueKey('transcript_jump_to_latest'),
                      heroTag: null,
                      tooltip: context.l10n.jumpToLatestMessage,
                      backgroundColor: const Color(0xFF35343B),
                      foregroundColor: Colors.white,
                      onPressed: () => _scrollToBottomGently(force: true),
                      child: const Icon(Icons.keyboard_arrow_down_rounded),
                    ),
                  ),
          ),
        ),
      ],
    );
  }

  int? _findChildIndex(Key key) {
    if (key == const ValueKey('transcript_header')) return 0;
    if (key == const ValueKey('transcript_bottom_spacing')) {
      return widget.leadingItems.length + widget.segments.length + 1;
    }
    if (key is! ValueKey<String>) return null;

    const leadingPrefix = 'transcript-leading-';
    const segmentPrefix = 'transcript-segment-';
    if (key.value.startsWith(leadingPrefix)) {
      final id = key.value.substring(leadingPrefix.length);
      final index = widget.leadingItemIds.indexOf(id);
      return index < 0 ? null : index + 1;
    }
    if (key.value.startsWith(segmentPrefix)) {
      final id = key.value.substring(segmentPrefix.length);
      final index = widget.segments.indexWhere((segment) => segment.id == id);
      return index < 0 ? null : widget.leadingItems.length + index + 1;
    }
    return null;
  }

  Widget _buildSegmentItem(int segmentIdx) {
    final data = widget.segments[segmentIdx];
    final Person? person = data.personId != null ? _getPersonById(data.personId) : null;
    final isTagging = widget.taggingSegmentIds.contains(data.id);
    final bool isUser = data.isUser;
    return Container(
      key: _segmentKeys[data.id],
      child: Padding(
        padding: EdgeInsetsDirectional.fromSTEB(
          widget.horizontalMargin ? 16 : 0,
          4.0,
          widget.horizontalMargin ? 16 : 0,
          4.0,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            if (!isUser) ...[
              // Avatar for other speakers (left side)
              GestureDetector(
                onTap: data.speakerId == omiSpeakerId
                    ? null
                    : () {
                        widget.editSegment?.call(data.id, data.speakerId);
                        PlatformManager.instance.analytics.tagSheetOpened();
                      },
                child: Column(
                  children: [
                    CircleAvatar(
                      radius: 16,
                      backgroundColor: _getSpeakerAvatarColor(isUser, data.speakerId, person),
                      child: _getSpeakerAvatar(data.speakerId, isUser, person),
                    ),
                    const SizedBox(height: 2),
                  ],
                ),
              ),
              const SizedBox(width: 8),
            ],

            // Message bubble
            Expanded(
              child: Column(
                crossAxisAlignment: isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
                children: [
                  if (!isUser) ...[
                    Padding(
                      padding: const EdgeInsets.only(left: 4, bottom: 2),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          GestureDetector(
                            onTap: data.speakerId == omiSpeakerId
                                ? null
                                : () {
                                    widget.editSegment?.call(data.id, data.speakerId);
                                    PlatformManager.instance.analytics.tagSheetOpened();
                                  },
                            child: Text(
                              data.speakerId == omiSpeakerId
                                  ? 'omi'
                                  : (person?.name ??
                                      context.l10n.speakerWithId(
                                        '${TranscriptSegment.getDisplaySpeakerId(data.speakerId, widget.segments)}',
                                      )),
                              style: TextStyle(
                                color: data.speakerId == omiSpeakerId || person != null
                                    ? Colors.grey.shade300
                                    : Colors.grey.shade400,
                                fontSize: 13,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ),
                          if (isTagging) ...[
                            const SizedBox(width: 6),
                            const SizedBox(
                              width: 12,
                              height: 12,
                              child: CircularProgressIndicator(
                                strokeWidth: 1.5,
                                valueColor: AlwaysStoppedAnimation(Colors.white),
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ],

                  // Chat bubble
                  Row(
                    mainAxisAlignment: isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
                    children: [
                      Flexible(
                        child: Container(
                          constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.75),
                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                          decoration: BoxDecoration(
                            color: _getSpeakerBubbleColor(isUser, data.speakerId, person),
                            borderRadius: BorderRadius.only(
                              topLeft: Radius.circular(
                                isUser
                                    ? 18
                                    : (segmentIdx > 0 && !widget.segments[segmentIdx - 1].isUser)
                                        ? 6
                                        : 18,
                              ),
                              topRight: Radius.circular(isUser ? 18 : 18),
                              bottomLeft: const Radius.circular(18),
                              bottomRight: Radius.circular(isUser ? 6 : 18),
                            ),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withValues(alpha: 0.15),
                                blurRadius: 4,
                                offset: const Offset(0, 1),
                              ),
                            ],
                          ),
                          child: SelectionArea(
                            child: GestureDetector(
                              behavior: HitTestBehavior.translucent,
                              onDoubleTap: widget.isConversationDetail && widget.onEditSegmentText != null
                                  ? () {
                                      HapticFeedback.mediumImpact();
                                      widget.onEditSegmentText!(segmentIdx);
                                    }
                                  : null,
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  _buildSegmentText(data, segmentIdx, isUser),
                                  if (data.translations.isNotEmpty) ...[
                                    const SizedBox(height: 8),
                                    ...data.translations.map(
                                      (translation) => Padding(
                                        padding: const EdgeInsets.only(top: 4),
                                        child: Text(
                                          _getDecodedText(translation.text),
                                          style: TextStyle(
                                            letterSpacing: 0.0,
                                            color: isUser
                                                ? Colors.white.withValues(alpha: 0.8)
                                                : Colors.grey.shade300.withValues(alpha: 0.8),
                                            fontSize: 14,
                                            fontStyle: FontStyle.italic,
                                            height: 1.3,
                                          ),
                                          textAlign: TextAlign.left,
                                        ),
                                      ),
                                    ),
                                    const SizedBox(height: 4),
                                    _buildTranslationNotice(),
                                  ],
                                  // Timestamp, provider, and play button
                                  if (widget.canDisplaySeconds ||
                                      data.sttProvider != null ||
                                      widget.onSegmentTap != null) ...[
                                    const SizedBox(height: 4),
                                    Row(
                                      mainAxisAlignment: MainAxisAlignment.end,
                                      children: [
                                        if (data.sttProvider != null) ...[
                                          Text(
                                            SttProviderConfig.getDisplayName(data.sttProvider),
                                            style: TextStyle(
                                              color:
                                                  isUser ? Colors.white.withValues(alpha: 0.5) : Colors.grey.shade500,
                                              fontSize: 10,
                                              fontStyle: FontStyle.italic,
                                            ),
                                          ),
                                          if (widget.canDisplaySeconds) ...[
                                            Text(
                                              ' · ',
                                              style: TextStyle(
                                                color:
                                                    isUser ? Colors.white.withValues(alpha: 0.5) : Colors.grey.shade500,
                                                fontSize: 10,
                                              ),
                                            ),
                                          ],
                                        ],
                                        // Play button for tap-to-seek
                                        if (widget.onSegmentTap != null) ...[
                                          GestureDetector(
                                            onTap: () {
                                              HapticFeedback.lightImpact();
                                              widget.onSegmentTap?.call(data);
                                            },
                                            child: Icon(
                                              Icons.play_circle_outline,
                                              size: 16,
                                              color:
                                                  isUser ? Colors.white.withValues(alpha: 0.7) : Colors.grey.shade400,
                                            ),
                                          ),
                                          const SizedBox(width: 6),
                                        ],
                                        if (widget.canDisplaySeconds)
                                          Text(
                                            data.getTimestampString(),
                                            style: TextStyle(
                                              color:
                                                  isUser ? Colors.white.withValues(alpha: 0.7) : Colors.grey.shade400,
                                              fontSize: 11,
                                            ),
                                          ),
                                      ],
                                    ),
                                  ],
                                ],
                              ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),

            if (isUser) ...[
              const SizedBox(width: 8),
              // Avatar for user (right side)
              GestureDetector(
                onTap: () {
                  widget.editSegment?.call(data.id, data.speakerId);
                  PlatformManager.instance.analytics.tagSheetOpened();
                },
                child: Column(
                  children: [
                    CircleAvatar(
                      radius: 16,
                      backgroundColor: _getSpeakerAvatarColor(isUser, data.speakerId, person),
                      child: _getSpeakerAvatar(data.speakerId, isUser, person),
                    ),
                    const SizedBox(height: 2),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildSegmentText(TranscriptSegment data, int segmentIdx, bool isUser) {
    final richText = RichText(
      textAlign: TextAlign.left,
      text: TextSpan(
        style: TextStyle(
          letterSpacing: 0.0,
          color: isUser ? Colors.white : Colors.grey.shade100,
          fontSize: 15,
          height: 1.4,
        ),
        children: widget.searchQuery.isNotEmpty
            ? _highlightSearchMatchesWithKeys(_getDecodedText(data.text), widget.searchQuery, segmentIdx)
            : [TextSpan(text: _getDecodedText(data.text))],
      ),
    );
    return richText;
  }

  Widget _buildTranslationNotice() {
    return GestureDetector(
      onTap: () {
        showDialog(
          context: context,
          builder: (BuildContext context) {
            return AlertDialog(
              title: Text(context.l10n.translationNotice),
              content: Text(context.l10n.translationNoticeMessage, style: const TextStyle(fontSize: 14)),
              actions: [
                TextButton(
                  child: Text(context.l10n.ok),
                  onPressed: () {
                    Navigator.of(context).pop();
                  },
                ),
              ],
            );
          },
        );
      },
      child: const Opacity(
        opacity: 0.5,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.check_circle, size: 12, color: Colors.grey),
            SizedBox(width: 4),
            Text(
              'translated by omi',
              style: TextStyle(fontSize: 12, color: Colors.grey, fontStyle: FontStyle.italic),
            ),
          ],
        ),
      ),
    );
  }
}

class LiteTranscriptWidget extends StatelessWidget {
  final List<TranscriptSegment> segments;

  const LiteTranscriptWidget({super.key, required this.segments});

  static String? _processText(List<TranscriptSegment> segments) {
    if (segments.isEmpty) return null;

    var text = getLastTranscript(segments, maxCount: 70, includeTimestamps: false);
    text = text.replaceAll(RegExp(r"\s+|\n+"), " ");
    // Add ellipsis at the start to indicate there's more content before
    return '...$text';
  }

  @override
  Widget build(BuildContext context) {
    final processedText = _processText(segments);
    if (processedText == null) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.fromLTRB(7, 0, 8, 0),
      child: Text(
        processedText,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: Theme.of(
          context,
        ).textTheme.bodyMedium!.copyWith(color: Colors.grey.shade300.withValues(alpha: 0.6), height: 1.3),
        textAlign: TextAlign.right,
      ),
    );
  }
}

String getLastTranscript(
  List<TranscriptSegment> transcriptSegments, {
  int? maxCount,
  bool generate = false,
  bool includeTimestamps = true,
}) {
  var transcript = TranscriptSegment.segmentsAsString(
    transcriptSegments.sublist(transcriptSegments.length >= 50 ? transcriptSegments.length - 50 : 0),
    includeTimestamps: includeTimestamps,
  );
  if (maxCount != null) transcript = transcript.substring(max(transcript.length - maxCount, 0));
  return tryDecodingText(transcript);
}

// Cache for decoded text
final Map<String, String> _decodedTextCache = {};

String tryDecodingText(String text) {
  if (!_decodedTextCache.containsKey(text)) {
    try {
      _decodedTextCache[text] = utf8.decode(text.toString().codeUnits);
    } catch (e) {
      _decodedTextCache[text] = text;
    }
  }
  return _decodedTextCache[text]!;
}

String formatChatTimestamp(DateTime dateTime, {BuildContext? context}) {
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final messageDate = DateTime(dateTime.year, dateTime.month, dateTime.day);
  final timeStr = dateTimeFormat('h:mm a', dateTime);

  if (messageDate == today) {
    // Today, show time only
    return timeStr;
  } else if (messageDate == today.subtract(const Duration(days: 1))) {
    // Yesterday
    if (context != null) {
      return context.l10n.yesterdayAtTime(timeStr);
    }
    return 'Yesterday $timeStr';
  } else {
    // Other days
    return dateTimeFormat('MMM d, h:mm a', dateTime);
  }
}
