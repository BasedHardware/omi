import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart' as api;
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// What Finish opens when the capture's conversation is not made yet: with conversations v3 the
/// server makes it from the recording once that is transcribed (1 to 10 minutes for batch audio).
/// The page says it is processing and turns into that conversation's page as soon as it is listed.
class FinishedCapturePage extends StatefulWidget {
  const FinishedCapturePage({
    super.key,
    required this.recordingId,
    this.fetch,
    this.pollInterval = const Duration(seconds: 5),
    this.maxWait = const Duration(minutes: 20),
    this.open,
  });

  /// The server's id for the finished recording (or, before v3, the conversation itself).
  final String recordingId;
  final Future<List<ServerConversation>> Function()? fetch;
  final Duration pollInterval;
  final Duration maxWait;

  /// Replaces this page with the conversation's; tests observe it instead.
  @visibleForTesting
  final void Function(BuildContext context, ServerConversation conversation)? open;

  /// The newest conversation made from [recordingId], which is the one on top of Home.
  /// Source recording IDs also link derived rows that have no audio pieces.
  static ServerConversation? match(Iterable<ServerConversation> rows, String recordingId) {
    ServerConversation? best;
    for (final row in rows) {
      final v3 = row.v3;
      if (row.discarded || v3?.recording == true) continue;
      final holds = row.id == recordingId ||
          v3?.recordingIds.contains(recordingId) == true ||
          v3?.recordingPieces.any((piece) => piece.recordingId == recordingId) == true;
      if (!holds) continue;
      if (best == null || row.createdAt.isAfter(best.createdAt)) best = row;
    }
    return best;
  }

  /// True when the server discarded what was made from [recordingId] (too short or no speech) and
  /// kept nothing: a discarded conversation holding a piece of it, or the recording itself marked
  /// discarded, with no kept conversation. The page then ends at once instead of waiting (C6).
  static bool discarded(Iterable<ServerConversation> rows, String recordingId) {
    if (match(rows, recordingId) != null) return false;
    for (final row in rows) {
      if (!row.discarded) continue;
      final v3 = row.v3;
      final holds =
          row.id == recordingId || (v3 != null && v3.recordingPieces.any((piece) => piece.recordingId == recordingId));
      if (holds) return true;
    }
    return false;
  }

  @override
  State<FinishedCapturePage> createState() => _FinishedCapturePageState();
}

/// Debug builds only: a shorter wait, so a simulator run can show the expired state.
const _debugMaxWait = int.fromEnvironment('OMI_FINISHED_CAPTURE_MAX_WAIT_SECONDS');

class _FinishedCapturePageState extends State<FinishedCapturePage> with WidgetsBindingObserver {
  Timer? _poll;
  bool _reading = false;
  bool _opened = false;
  bool _expired = false;
  bool _discarded = false;
  Timer? _expiry;
  StreamSubscription<SummaryWaitAnswer>? _summaryAnswers;

  /// Reads in a row that got no answer. After [_failedReadsShown] the page says it could not check,
  /// with Try Again, instead of claiming it is still working (X10).
  int _failedReads = 0;
  static const _failedReadsShown = 3;
  bool get _readsFailing => _failedReads >= _failedReadsShown;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _poll = Timer.periodic(widget.pollInterval, (_) => _check());
    _expiry = Timer(_debugMaxWait > 0 && kDebugMode ? const Duration(seconds: _debugMaxWait) : widget.maxWait, _expire);
    // Reliability experiment fast_end_feedback: the app's waiting request may return the conversation
    // made from this recording before the next poll does; open it then. Off, nothing is ever emitted.
    _summaryAnswers =
        Provider.of<ConversationsV3Provider?>(context, listen: false)?.summaryAnswers.listen(_onSummaryAnswer);
    unawaited(_check());
  }

  void _onSummaryAnswer(SummaryWaitAnswer answer) {
    final row = answer.result.item;
    if (row == null || _opened || _discarded || !mounted) return;
    final found = FinishedCapturePage.match([row], widget.recordingId);
    if (found != null && ModalRoute.of(context)?.isCurrent == true) _open(found);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Back from the background, read once whatever the wait: it may have arrived meanwhile.
    if (state == AppLifecycleState.resumed) unawaited(_check());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _poll?.cancel();
    _expiry?.cancel();
    unawaited(_summaryAnswers?.cancel());
    super.dispose();
  }

  Future<void> _check() async {
    if (_reading || _opened || _discarded || !mounted) return;
    _reading = true;
    try {
      final rows = await (widget.fetch ?? _defaultFetch)();
      if (_failedReads > 0 && mounted) setState(() => _failedReads = 0);
      final found = FinishedCapturePage.match(rows, widget.recordingId);
      if (found != null && mounted && !_opened) {
        final route = ModalRoute.of(context);
        if (route != null && route.isCurrent) return _open(found);
      }
      if (found == null && mounted && !_opened && FinishedCapturePage.discarded(rows, widget.recordingId)) {
        _poll?.cancel();
        _expiry?.cancel();
        setState(() => _discarded = true);
      }
    } catch (_) {
      // Offline or a failed read: the next tick tries again, and repeated failures are said (X10).
      if (mounted) setState(() => _failedReads++);
    } finally {
      _reading = false;
    }
  }

  /// A failed list read throws, so it counts as a failed read rather than "not there yet".
  static Future<List<ServerConversation>> _defaultFetch() async {
    final result = await api.getConversationsResult(limit: 10, includeDiscarded: true);
    if (!result.ok) throw StateError('conversation list read failed');
    return result.items;
  }

  /// Try Again after failed reads: read now, and keep polling until the wait runs out.
  void _retryReads() {
    setState(() {
      _failedReads = 0;
      _expired = false;
    });
    _poll?.cancel();
    _poll = Timer.periodic(widget.pollInterval, (_) => _check());
    _expiry?.cancel();
    _expiry = Timer(widget.maxWait, _expire);
    unawaited(_check());
  }

  /// After [FinishedCapturePage.maxWait] it stops polling and says so; Home shows the conversation
  /// whenever it lands, and a resume still reads once.
  void _expire() {
    if (_opened || !mounted) return;
    _poll?.cancel();
    setState(() => _expired = true);
  }

  void _open(ServerConversation found) {
    _opened = true;
    _poll?.cancel();
    _expiry?.cancel();
    // Home shows it as its top row when the reader goes back.
    unawaited(context.read<ConversationProvider?>()?.fetchConversations());
    final open = widget.open;
    if (open != null) return open(context, found);
    unawaited(Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => ConversationDetailPage(conversation: found)),
    ));
  }

  void _backToHome() {
    context.read<HomeProvider?>()?.setIndex(HomeProvider.homeTab);
    Navigator.of(context).maybePop();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Scaffold(
      appBar: AppBar(automaticallyImplyLeading: false, leading: const Center(child: OmiBackButton.circled())),
      body: _discarded
          ? OmiEmptyState(
              key: const Key('finished_capture_discarded'),
              icon: Icons.mic_off_outlined,
              title: l10n.finishNothingKeptTitle,
              message: l10n.discardedOnlyRecording,
              action: OmiButton.secondary(label: l10n.finishBackToHome, onPressed: _backToHome),
            )
          // Reads keep failing: say so with Try Again; "still working" only after a read that answered.
          : _readsFailing
              ? OmiErrorState(
                  key: const Key('finished_capture_read_failed'),
                  message: l10n.couldNotCheckOnIt,
                  retryLabel: l10n.tryAgain,
                  onRetry: _retryReads,
                )
              : _expired
                  ? OmiErrorState(
                      key: const Key('finished_capture_expired'),
                      message: l10n.takingLongerThanUsual,
                      retryLabel: l10n.finishBackToHome,
                      onRetry: _backToHome,
                    )
                  : OmiLoadingState(
                      key: const Key('finished_capture_processing'), label: l10n.conversationWritingSummary),
    );
  }
}
