part of 'transcript.dart';

/// Rebuilds one transcript line only when that line gains or loses the playhead
/// highlight. A reader fling moves the highlight often; rebuilding the list for
/// each move lays out every visible line again.
class _SegmentHighlight extends StatefulWidget {
  const _SegmentHighlight({
    required this.segmentId,
    required this.highlighted,
    required this.staticCurrent,
    required this.builder,
  });

  final String segmentId;
  final ValueListenable<String?>? highlighted;
  final bool staticCurrent;
  final Widget Function(BuildContext context, bool isCurrent) builder;

  @override
  State<_SegmentHighlight> createState() => _SegmentHighlightState();
}

class _SegmentHighlightState extends State<_SegmentHighlight> {
  ValueListenable<String?>? _highlighted;
  late bool _current;

  @override
  void initState() {
    super.initState();
    _current = _isCurrent;
    _subscribe(widget.highlighted);
  }

  @override
  void didUpdateWidget(_SegmentHighlight oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.highlighted != widget.highlighted || oldWidget.segmentId != widget.segmentId) {
      _unsubscribe();
      _current = _isCurrent;
      _subscribe(widget.highlighted);
    } else {
      _current = _isCurrent;
    }
  }

  @override
  void dispose() {
    _unsubscribe();
    super.dispose();
  }

  bool get _isCurrent {
    final highlighted = widget.highlighted;
    if (highlighted != null) return highlighted.value == widget.segmentId;
    return widget.staticCurrent;
  }

  void _subscribe(ValueListenable<String?>? highlighted) {
    _highlighted = highlighted;
    highlighted?.addListener(_onHighlight);
  }

  void _unsubscribe() {
    _highlighted?.removeListener(_onHighlight);
    _highlighted = null;
  }

  void _onHighlight() {
    if (!mounted) return;
    final next = _isCurrent;
    if (next == _current) return;
    _current = next;
    // updateSegments() can sync the highlight from a parent build. That build
    // already includes this line; setState here would assert.
    final phase = SchedulerBinding.instance.schedulerPhase;
    if (phase == SchedulerPhase.persistentCallbacks || phase == SchedulerPhase.midFrameMicrotasks) return;
    setState(() {});
  }

  @override
  Widget build(BuildContext context) => widget.builder(context, _isCurrent);
}

// Measure the upward-growing history before paint. A post-frame anchor change
// leaves short transcripts below the viewport for their first frame.
class _LiveTranscriptScrollView extends CustomScrollView {
  const _LiveTranscriptScrollView(
      {super.key, super.controller, super.center, super.slivers, required this.startAtLatest});

  final bool startAtLatest;

  @override
  Widget buildViewport(BuildContext context, ViewportOffset offset, AxisDirection axisDirection, List<Widget> slivers) {
    return _LiveTranscriptViewport(offset: offset, center: center, slivers: slivers, startAtLatest: startAtLatest);
  }
}

class _LiveTranscriptViewport extends Viewport {
  _LiveTranscriptViewport({required super.offset, super.center, required super.slivers, required this.startAtLatest});

  final bool startAtLatest;

  @override
  RenderViewport createRenderObject(BuildContext context) => _LiveTranscriptRenderViewport(
        offset: offset,
        startAtLatest: startAtLatest,
        crossAxisDirection: Viewport.getDefaultCrossAxisDirection(context, AxisDirection.down),
      );

  @override
  void updateRenderObject(BuildContext context, RenderViewport renderObject) {
    // The render object owns its measured anchor; don't reset it on rebuild.
    renderObject
      ..offset = offset
      ..crossAxisDirection = Viewport.getDefaultCrossAxisDirection(context, AxisDirection.down);
  }
}

class _LiveTranscriptRenderViewport extends RenderViewport {
  _LiveTranscriptRenderViewport({required super.offset, required super.crossAxisDirection, required bool startAtLatest})
      : _initialFollow = startAtLatest,
        super(anchor: 1);

  bool _initialFollow;
  bool _hasMeasuredAnchor = false;

  double _measuredAnchor = 1;

  @override
  double get anchor => _measuredAnchor;

  @override
  void performLayout() {
    super.performLayout();
    // The first sliver contains history in reverse growth order. Its extent is
    // exact when it fits; a long history only lays out the live-edge window.
    final extent = firstChild?.geometry?.scrollExtent;
    if (extent == null || size.height == 0) return;
    final nextAnchor = (extent / size.height).clamp(0.0, 1.0);
    final leadingEdgeShift = (nextAnchor - anchor) * size.height;
    final anchorChanged = leadingEdgeShift != 0;
    if (_hasMeasuredAnchor && anchorChanged) {
      // Changing the anchor moves the center's leading edge even when pixels
      // hasn't changed. Keep the reader's rows fixed before paint, including
      // during drags and flings; a post-frame jump would interrupt the gesture.
      // The next layout applies the corrected dimensions, so ballistic motion
      // also continues from the corrected position rather than its old origin.
      offset.correctBy(leadingEdgeShift);
    }
    _measuredAnchor = nextAnchor;
    _hasMeasuredAnchor = true;
    final initialFollow = _initialFollow;
    _initialFollow = false;
    if (initialFollow) {
      // On creation the center contains only the newest row and footer. Both
      // are measured here, so opening needs no post-frame jump to reveal them.
      final latest = max(0.0, (center?.geometry?.scrollExtent ?? 0) - size.height * (1 - anchor));
      offset.correctBy(latest - offset.pixels);
    }
    if (anchorChanged || initialFollow) super.performLayout();
  }
}
