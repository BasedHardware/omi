// The summary of a live or unsummarised v3 conversation: the pen and "Writing your summary…" over a
// skeleton while it is written, then the sections streamed in; polls on a 409 and offers Try Again on failure.

import 'dart:async';

import 'package:clock/clock.dart';

import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/conversations_v3.dart';
import 'package:omi/services/conversation_summary_stream.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_markdown_widget.dart';
import 'package:omi/pages/conversations/widgets/conversation_state_tile.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

typedef SummaryStreamOpener = Stream<SummaryStreamEvent> Function(String conversationId);

/// The summary of a v3 conversation that is still going or still being written, written when the
/// page opens. The server answers at once with a fresh stored summary, streams a new one section by
/// section, or (another writer holds it) answers 409, and the page then re-reads the conversation
/// every 2 s for up to 60 s. A pen and "Writing your summary…" sit over a skeleton until the first
/// section arrives and stay until the summary is stored; the page then shows the stored summary.
class LiveSummarySection extends StatefulWidget {
  const LiveSummarySection({
    super.key,
    required this.conversation,
    required this.refresh,
    required this.onActiveChanged,
    this.stream,
    this.pollInterval = const Duration(seconds: 2),
    this.pollFor = const Duration(seconds: 60),
  });

  final ServerConversation conversation;

  /// Re-reads the open conversation into the page; true when a fresh read landed.
  final Future<bool> Function() refresh;

  /// True while this section stands in for the page's summary.
  final ValueChanged<bool> onActiveChanged;
  final SummaryStreamOpener? stream;

  /// Test seam for the page-level section, which the summary tab builds without a [stream].
  @visibleForTesting
  static SummaryStreamOpener? debugStream;
  final Duration pollInterval;
  final Duration pollFor;

  /// A v3 conversation in progress, or one whose summary is being written.
  static bool wants(ServerConversation? conversation) {
    final state = conversation?.v3?.tileState;
    return state == ConversationTileState.live || state == ConversationTileState.writing;
  }

  @override
  State<LiveSummarySection> createState() => _LiveSummarySectionState();
}

enum _Phase { writing, polling, written, failed, finished }

class _LiveSummarySectionState extends State<LiveSummarySection> {
  _Phase _phase = _Phase.writing;
  final List<String> _sections = [];
  StreamSubscription<SummaryStreamEvent>? _subscription;
  final Completer<void> _cancel = Completer<void>();
  Timer? _poll;
  String? _openedId;

  @override
  void initState() {
    super.initState();
    _begin();
  }

  @override
  void didUpdateWidget(covariant LiveSummarySection oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.conversation.id != _openedId) {
      _stop();
      _sections.clear();
      _phase = _Phase.writing;
      _begin();
    } else if (_phase == _Phase.polling && _landed(widget.conversation)) {
      _finish();
    }
  }

  DateTime? _coveredAtOpen;

  /// The stored summary moved on since the page opened, or the conversation is done.
  bool _landed(ServerConversation c) {
    final covers = c.v3?.summaryCoversThrough;
    if (covers != null && (_coveredAtOpen == null || covers.isAfter(_coveredAtOpen!))) return true;
    return c.v3?.tileState == ConversationTileState.done;
  }

  void _begin() {
    _openedId = widget.conversation.id;
    _coveredAtOpen = widget.conversation.v3?.summaryCoversThrough;
    _active(true);
    final open = widget.stream ??
        LiveSummarySection.debugStream ??
        (String id) => streamConversationSummary(id, cancelSignal: _cancel.isCompleted ? null : _cancel.future);
    _subscription = open(widget.conversation.id).listen(_onEvent, onError: (_) => _fail());
  }

  void _onEvent(SummaryStreamEvent event) {
    if (!mounted) return;
    switch (event) {
      case SummarySection(:final markdown):
        if (markdown.trim().isEmpty) return;
        setState(() => _sections.add(markdown));
      case SummaryDone(:final structured):
        // The page shows the stored summary once it re-reads the conversation. If that read fails,
        // keep what was written up: the streamed sections, or the summary the done frame carried.
        unawaited(widget.refresh().then((ok) => ok ? _finish() : _keep(structured.overview),
            onError: (Object _) => _keep(structured.overview)));
      case SummaryInProgress():
        _startPolling();
      case SummaryFailed():
        _fail();
    }
  }

  void _startPolling() {
    if (_phase == _Phase.polling) return;
    setState(() => _phase = _Phase.polling);
    // One read at a time, inside a wall-clock window: each read is bounded by the time left.
    final deadline = clock.now().add(widget.pollFor);
    void next() {
      _poll = Timer(widget.pollInterval, () async {
        if (!mounted || _phase != _Phase.polling) return;
        final left = deadline.difference(clock.now());
        if (left <= Duration.zero) {
          // Nothing landed in time: an older summary shows; with none, offer to try again.
          _fail();
          return;
        }
        try {
          await widget.refresh().timeout(left);
        } catch (_) {}
        if (mounted && _phase == _Phase.polling) next();
      });
    }

    next();
  }

  void _keep(String overview) {
    if (_sections.isEmpty && overview.trim().isNotEmpty) _sections.add(overview);
    _sections.isEmpty ? _finish() : _written();
  }

  void _written() {
    _stop();
    if (mounted) setState(() => _phase = _Phase.written);
  }

  /// No summary could be written now. With an older summary stored the page shows it; with none,
  /// this section offers to try again rather than leaving the page's generic Generate button on a
  /// conversation that is still going.
  void _fail() {
    if (widget.conversation.v3?.summaryCoversThrough != null) {
      _finish();
      return;
    }
    _stop();
    if (mounted) setState(() => _phase = _Phase.failed);
  }

  void _retry() {
    _stop();
    setState(() {
      _sections.clear();
      _phase = _Phase.writing;
    });
    _begin();
  }

  void _finish() {
    _stop();
    if (!mounted || _phase == _Phase.finished) return;
    setState(() => _phase = _Phase.finished);
    _active(false);
  }

  void _active(bool active) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) widget.onActiveChanged(active);
    });
  }

  void _stop() {
    _poll?.cancel();
    _poll = null;
    unawaited(_subscription?.cancel());
    _subscription = null;
  }

  @override
  void dispose() {
    _stop();
    if (!_cancel.isCompleted) _cancel.complete();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_phase == _Phase.finished) return const SliverToBoxAdapter(child: SizedBox.shrink());
    if (_phase == _Phase.failed) {
      return SliverToBoxAdapter(
        child: Padding(
          padding: const EdgeInsets.only(top: 4, bottom: 12),
          child: Row(
            key: const Key('live_summary_failed'),
            children: [
              Expanded(
                child: Text(context.l10n.somethingWentWrong,
                    style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
              ),
              OmiButton.secondary(label: context.l10n.tryAgain, onPressed: _retry, size: OmiButtonSize.compact),
            ],
          ),
        ),
      );
    }
    if (_phase == _Phase.written) {
      return ConversationMarkdownSliver(key: const Key('live_summary_sections'), content: _sections.join('\n\n'));
    }
    return SliverMainAxisGroup(slivers: [
      SliverToBoxAdapter(
        child: Padding(
          padding: const EdgeInsets.only(top: 4, bottom: 12),
          child: Semantics(
            liveRegion: true,
            child: Row(
              key: const Key('live_summary_writing'),
              children: [
                const ConversationWritingPen(size: 16),
                const SizedBox(width: 8),
                Text(context.l10n.conversationWritingSummary,
                    style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
              ],
            ),
          ),
        ),
      ),
      if (_sections.isEmpty)
        const SliverToBoxAdapter(child: _SummarySkeleton())
      else
        ConversationMarkdownSliver(
          key: const Key('live_summary_sections'),
          content: _sections.join('\n\n'),
        ),
    ]);
  }
}

/// Three soft lines where the summary will be.
class _SummarySkeleton extends StatefulWidget {
  const _SummarySkeleton();

  @override
  State<_SummarySkeleton> createState() => _SummarySkeletonState();
}

class _SummarySkeletonState extends State<_SummarySkeleton> with SingleTickerProviderStateMixin {
  late final AnimationController _shimmer =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1400));

  @override
  void dispose() {
    _shimmer.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reduceMotion = OmiMotion.of(context).standard == Duration.zero;
    final animate = !reduceMotion && TickerMode.valuesOf(context).enabled;
    if (animate) {
      if (!_shimmer.isAnimating) _shimmer.repeat(reverse: true);
    } else if (_shimmer.isAnimating) {
      _shimmer.stop();
    }
    Widget line(double widthFactor) => FractionallySizedBox(
          alignment: AlignmentDirectional.centerStart,
          widthFactor: widthFactor,
          child: Container(
            height: 12,
            margin: const EdgeInsets.symmetric(vertical: 6),
            decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
          ),
        );
    final lines = Column(
      key: const Key('live_summary_skeleton'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [line(1), line(0.92), line(0.7), const SizedBox(height: 10), line(0.85), line(0.6)],
    );
    if (!animate) return lines;
    return FadeTransition(opacity: Tween<double>(begin: 1, end: 0.5).animate(_shimmer), child: lines);
  }
}
