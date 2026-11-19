import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart' as api;
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/conversation_provider.dart';
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

  /// The conversation made from [recordingId]: the newest one holding a piece of it, which is the
  /// one on top of Home. A recording document itself, or a row with no piece of it (an unrelated
  /// sync copy), never matches.
  static ServerConversation? match(Iterable<ServerConversation> rows, String recordingId) {
    ServerConversation? best;
    for (final row in rows) {
      final v3 = row.v3;
      if (row.discarded || v3?.recording == true) continue;
      final holds = v3 != null
          ? v3.recordingPieces.any((piece) => piece.recordingId == recordingId) || row.id == recordingId
          : row.id == recordingId;
      if (!holds) continue;
      if (best == null || row.createdAt.isAfter(best.createdAt)) best = row;
    }
    return best;
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
  Timer? _expiry;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _poll = Timer.periodic(widget.pollInterval, (_) => _check());
    _expiry = Timer(_debugMaxWait > 0 && kDebugMode ? const Duration(seconds: _debugMaxWait) : widget.maxWait, _expire);
    unawaited(_check());
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
    super.dispose();
  }

  Future<void> _check() async {
    if (_reading || _opened || !mounted) return;
    _reading = true;
    try {
      final rows = await (widget.fetch ?? () => api.getConversations(limit: 10))();
      final found = FinishedCapturePage.match(rows, widget.recordingId);
      if (found != null && mounted && !_opened) {
        final route = ModalRoute.of(context);
        if (route != null && route.isCurrent) return _open(found);
      }
    } catch (_) {
      // Offline or a failed read: the next tick tries again.
    } finally {
      _reading = false;
    }
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
      body: _expired
          ? OmiErrorState(
              key: const Key('finished_capture_expired'),
              message: l10n.finishStillProcessing,
              retryLabel: l10n.finishBackToHome,
              onRetry: _backToHome,
            )
          : OmiLoadingState(key: const Key('finished_capture_processing'), label: l10n.processingConversationProgress),
    );
  }
}
