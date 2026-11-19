import 'dart:async';

import 'package:clock/clock.dart';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/conversations_v3.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/conversation_summary_stream.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/conversation_summary_selection.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_markdown_widget.dart';
import 'package:omi/pages/conversation_detail/live_conversation_refresher.dart';
import 'package:omi/pages/conversations/widgets/conversation_state_tile.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

typedef SummaryStreamOpener = Stream<SummaryStreamEvent> Function(String conversationId);

/// The summary of a v3 conversation that is still going or still being written.
///
/// Opening a live conversation only reads its stored state. Catch me up requests a summary
/// explicitly. The detail page refreshes live speech and pending transcription; once
/// the transcript is ready, keep the normal final-summary streaming handoff.
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

  /// A v3 conversation in progress, ended with its transcript still arriving, or one whose summary is
  /// being written.
  static bool wants(ServerConversation? conversation) {
    final state = conversation?.v3?.tileState;
    return LiveConversationRefresher.awaitsSummary(conversation) || state == ConversationTileState.writing;
  }

  @override
  State<LiveSummarySection> createState() => _LiveSummarySectionState();
}

enum _Phase { live, writing, polling, written, failed, finished }

class _LiveSummarySectionState extends State<LiveSummarySection> {
  _Phase _phase = _Phase.writing;
  final List<String> _sections = [];
  StreamSubscription<SummaryStreamEvent>? _subscription;
  Completer<void>? _cancel;
  Timer? _poll;
  bool _liveRequestFailed = false;
  int _requestEpoch = 0;
  List<Object>? _requestSpeech;
  ({DateTime through, String markdown})? _liveResult;
  String? _openedId;
  late String _ownerUid;

  @override
  void initState() {
    super.initState();
    _ownerUid = SharedPreferencesUtil().uid;
    _begin();
  }

  @override
  void didUpdateWidget(covariant LiveSummarySection oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.conversation.id != _openedId) {
      _stop();
      _sections.clear();
      _ownerUid = SharedPreferencesUtil().uid;
      _liveResult = null;
      _liveRequestFailed = false;
      _phase = _Phase.writing;
      _begin();
    } else if (_awaitsSummary(oldWidget.conversation) != _awaitsSummary(widget.conversation)) {
      _stop();
      _sections.clear();
      _liveResult = null;
      _liveRequestFailed = false;
      _phase = _Phase.writing;
      _begin();
    } else if (_isLive(oldWidget.conversation) != _isLive(widget.conversation)) {
      // A live request can no longer apply once Finish leaves the transcript pending.
      _stopRequest();
      _sections.clear();
      _liveResult = null;
      _liveRequestFailed = false;
      _phase = _Phase.live;
    } else {
      if (_isLive(widget.conversation) && !identical(oldWidget.conversation, widget.conversation)) {
        // A new detail snapshot supersedes optimistic SSE. It exposes stored preview coverage only
        // when the server verified it against the current transcript receipt.
        _liveResult = null;
        if (!_canShowLiveContent ||
            (_requestSpeech != null && !listEquals(_requestSpeech, _speechSnapshot(widget.conversation)))) {
          _stopRequest();
          _sections.clear();
          _liveRequestFailed = false;
          _phase = _Phase.live;
        }
      }
      if (_phase == _Phase.polling && _landed(widget.conversation)) _finish();
    }
  }

  DateTime? _coveredAtOpen;
  ({DateTime through, String markdown})? _liveSummaryAtRequest;

  /// The stored summary moved on since the page opened, or the conversation is done.
  bool _landed(ServerConversation c) {
    if (_isLive(c)) {
      final previous = _liveSummaryAtRequest;
      final stored = _storedSummary;
      return stored != null &&
          (previous == null ||
              stored.through.isAfter(previous.through) ||
              (stored.through.isAtSameMomentAs(previous.through) && stored.markdown != previous.markdown));
    }
    final covers = c.v3?.summaryCoversThrough;
    if (covers != null && (_coveredAtOpen == null || covers.isAfter(_coveredAtOpen!))) return true;
    return c.v3?.tileState == ConversationTileState.done;
  }

  static bool _awaitsSummary(ServerConversation c) => LiveConversationRefresher.awaitsSummary(c);

  static bool _isLive(ServerConversation c) => c.v3?.tileState == ConversationTileState.live;

  void _begin() {
    _openedId = widget.conversation.id;
    _coveredAtOpen = widget.conversation.v3?.summaryCoversThrough;
    _active(true);
    if (_awaitsSummary(widget.conversation)) {
      // The page keeps the conversation current; didUpdateWidget starts the write when it moves on.
      _phase = _Phase.live;
      return;
    }
    _startStream();
  }

  void _startStream({bool liveCatchup = false}) {
    _stopRequest();
    final request = _requestEpoch;
    final cancel = _cancel = Completer<void>();
    _requestSpeech = liveCatchup ? _speechSnapshot(widget.conversation) : null;
    bool liveTarget() =>
        request == _requestEpoch &&
        _ownerUid.isNotEmpty &&
        _currentLiveTarget &&
        _canShowLiveContent &&
        listEquals(_requestSpeech, _speechSnapshot(widget.conversation));
    _liveSummaryAtRequest = liveCatchup ? _summary : null;
    _coveredAtOpen = widget.conversation.v3?.summaryCoversThrough;
    final open = widget.stream ??
        LiveSummarySection.debugStream ??
        (String id) => streamConversationSummary(
              id,
              liveCatchup: liveCatchup,
              cancelSignal: cancel.future,
              canDispatch: liveCatchup ? liveTarget : null,
            );
    _subscription = open(widget.conversation.id).listen(
      (event) {
        if (!mounted || request != _requestEpoch) return;
        if (liveCatchup && !liveTarget()) {
          _finish();
          return;
        }
        _onEvent(event, liveCatchup: liveCatchup);
      },
      onError: (Object _) {
        if (!mounted || request != _requestEpoch) return;
        liveCatchup && !liveTarget() ? _finish() : _fail();
      },
    );
  }

  void _catchUp() {
    if (!_currentLiveTarget || _phase != _Phase.live || !_canCatchUp) return;
    setState(() {
      _sections.clear();
      _liveRequestFailed = false;
      _phase = _Phase.writing;
    });
    _startStream(liveCatchup: true);
  }

  void _onEvent(SummaryStreamEvent event, {required bool liveCatchup}) {
    switch (event) {
      case SummarySection(:final markdown):
        if (markdown.trim().isEmpty) return;
        setState(() => _sections.add(markdown));
      case SummaryDone(:final structured, :final coversThrough):
        if (liveCatchup) {
          final body = _markdown(structured);
          if (coversThrough != null && body.isNotEmpty) {
            _liveResult = (through: coversThrough, markdown: body);
          } else {
            _liveRequestFailed = true;
          }
          _finish();
          return;
        }
        // Retain the final stream's fallback when the follow-up read is unavailable.
        final request = _requestEpoch;
        void keep() {
          if (mounted && request == _requestEpoch) _keep(structured.overview);
        }

        unawaited(widget.refresh().then((ok) {
          if (!mounted || request != _requestEpoch) return;
          ok ? _finish() : keep();
        }, onError: (Object _) => keep()));
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
    final request = _requestEpoch;
    void next() {
      _poll = Timer(widget.pollInterval, () async {
        if (!mounted || request != _requestEpoch || _phase != _Phase.polling) return;
        if (_isLive(widget.conversation) && !_currentLiveTarget) {
          _finish();
          return;
        }
        final left = deadline.difference(clock.now());
        if (left <= Duration.zero) {
          // Nothing landed in time: an older summary shows; with none, offer to try again.
          _fail();
          return;
        }
        try {
          await widget.refresh().timeout(left);
        } catch (_) {}
        if (mounted && request == _requestEpoch && _phase == _Phase.polling) next();
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
    if (_isLive(widget.conversation)) {
      _stopRequest();
      if (mounted)
        setState(() {
          _liveRequestFailed = true;
          _phase = _Phase.live;
        });
      return;
    }
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
    if (_isLive(widget.conversation)) {
      _stopRequest();
      if (mounted) setState(() => _phase = _Phase.live);
      return;
    }
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
    _stopRequest();
  }

  void _stopRequest() {
    _requestEpoch++;
    _requestSpeech = null;
    _cancel?.complete();
    _cancel = null;
    _poll?.cancel();
    _poll = null;
    unawaited(_subscription?.cancel());
    _subscription = null;
  }

  @override
  void dispose() {
    _stop();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_isLive(widget.conversation)) return _buildLive(context);
    if (_awaitsSummary(widget.conversation)) {
      return SliverToBoxAdapter(
        child: Padding(
          padding: const EdgeInsets.only(top: 4, bottom: 12),
          child: Semantics(
            liveRegion: true,
            child: Text(context.l10n.transcribing, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
          ),
        ),
      );
    }
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

  static String _markdown(Structured structured) {
    final overview = structured.overview.trim();
    return overview.isNotEmpty ? overview : ConversationSummarySelection.renderSections(structured.sections);
  }

  ({DateTime through, String markdown})? get _storedSummary {
    final c = widget.conversation;
    if (!_canShowLiveContent) return null;
    final through = c.v3?.summaryCoversThrough;
    final live = c.v3?.liveSummary;
    if (live != null && (through == null || !live.coversThrough.isBefore(through))) {
      final markdown = _markdown(live.structured);
      if (markdown.isNotEmpty) return (through: live.coversThrough, markdown: markdown);
    }
    final markdown = _markdown(c.structured);
    return through == null || markdown.isEmpty ? null : (through: through, markdown: markdown);
  }

  ({DateTime through, String markdown})? get _summary {
    if (!_canShowLiveContent) return null;
    final stored = _storedSummary;
    final result = _liveResult;
    return result != null && (stored == null || !result.through.isBefore(stored.through)) ? result : stored;
  }

  bool get _currentLiveTarget =>
      mounted &&
      widget.conversation.id == _openedId &&
      _ownerUid == SharedPreferencesUtil().uid &&
      _isLive(widget.conversation) &&
      ModalRoute.isCurrentOf(context) != false;

  bool get _canShowLiveContent {
    final c = widget.conversation;
    return !c.isLocked && !c.discarded && c.v3?.homeHidden != true && c.v3?.recording != true;
  }

  static List<Object> _speechSnapshot(ServerConversation c) => [
        for (final segment in c.transcriptSegments)
          (segment.id, segment.text, segment.start, segment.end, segment.speaker, segment.isUser, segment.personId),
      ];

  static final _words = RegExp(r'\S+');

  bool get _enoughTranscript {
    var words = 0;
    for (final segment in widget.conversation.transcriptSegments) {
      words += _words.allMatches(segment.text).length;
      if (words >= 300) return true;
    }
    return false;
  }

  bool get _canCatchUp {
    final c = widget.conversation;
    return _ownerUid.isNotEmpty &&
        _canShowLiveContent &&
        c.v3?.kind != 'media' &&
        c.v3?.kind != 'background' &&
        _enoughTranscript;
  }

  Widget _buildLive(BuildContext context) {
    if (_ownerUid != SharedPreferencesUtil().uid || !_canShowLiveContent) {
      return const SliverToBoxAdapter(child: SizedBox.shrink());
    }
    final summary = _summary;
    final waiting = _phase == _Phase.writing || _phase == _Phase.polling;
    final transcript = widget.conversation.transcriptSegments.reversed
        .map((segment) => segment.text.trim())
        .where((text) => text.isNotEmpty)
        .take(3)
        .toList()
        .reversed
        .join('\n');
    final style = OmiType.subhead.copyWith(color: OmiColors.textSecondary);
    final coverage = waiting && _sections.isNotEmpty ? null : summary?.through.toLocal();
    final localizations = MaterialLocalizations.of(context);
    final timestamp = coverage == null
        ? null
        : '${localizations.formatShortDate(coverage)} ${localizations.formatTimeOfDay(TimeOfDay.fromDateTime(coverage), alwaysUse24HourFormat: MediaQuery.alwaysUse24HourFormatOf(context))}';
    return SliverMainAxisGroup(
      key: const Key('live_summary_in_progress'),
      slivers: [
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.only(top: 4, bottom: 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (timestamp != null)
                  Text(context.l10n.conversationSummaryThrough(timestamp),
                      key: const Key('live_summary_coverage'), style: style),
                if (waiting)
                  Row(
                    key: const Key('live_summary_writing'),
                    children: [
                      const ConversationWritingPen(size: 16),
                      const SizedBox(width: 8),
                      Text(context.l10n.conversationWritingSummary, style: style),
                    ],
                  )
                else if (_canCatchUp)
                  OmiButton.secondary(
                    key: const Key('live_summary_catch_up'),
                    label: context.l10n.conversationCatchMeUp,
                    onPressed: _catchUp,
                    size: OmiButtonSize.compact,
                  ),
                if (_liveRequestFailed) Text(context.l10n.somethingWentWrong, style: style),
                if (summary == null && !waiting && !_enoughTranscript)
                  if (transcript.isEmpty)
                    Text(context.l10n.conversationSummaryWhenItEnds, style: style)
                  else ...[
                    Text(context.l10n.conversationRecentTranscript, style: style),
                    const SizedBox(height: 8),
                    Text(transcript,
                        key: const Key('live_summary_recent_transcript'), maxLines: 8, overflow: TextOverflow.ellipsis),
                  ],
              ],
            ),
          ),
        ),
        if (waiting && _sections.isNotEmpty)
          ConversationMarkdownSliver(key: const Key('live_summary_sections'), content: _sections.join('\n\n'))
        else if (summary != null)
          ConversationMarkdownSliver(key: const Key('live_summary_stored'), content: summary.markdown)
        else if (waiting)
          const SliverToBoxAdapter(child: _SummarySkeleton()),
      ],
    );
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
