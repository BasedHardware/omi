import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart' as api;
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/widgets.dart' show SummaryWaitingNotice;
import 'package:omi/providers/conversation_provider.dart';
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

class _FinishedCapturePageState extends State<FinishedCapturePage> with WidgetsBindingObserver {
  Timer? _poll;
  bool _reading = false;
  bool _opened = false;
  late final DateTime _since = DateTime.now();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _poll = Timer.periodic(widget.pollInterval, (_) => _check());
    unawaited(_check());
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) unawaited(_check());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _check() async {
    if (_reading || _opened || !mounted) return;
    if (DateTime.now().difference(_since) > widget.maxWait) {
      _poll?.cancel();
      return;
    }
    _reading = true;
    try {
      final rows = await (widget.fetch ?? () => api.getConversations(limit: 10))();
      final found = FinishedCapturePage.match(rows, widget.recordingId);
      if (found == null || !mounted || _opened) return;
      final route = ModalRoute.of(context);
      if (route == null || !route.isCurrent) return;
      _opened = true;
      _poll?.cancel();
      // Home shows it as its top row when the reader goes back.
      unawaited(context.read<ConversationProvider?>()?.fetchConversations());
      final open = widget.open;
      if (open != null) return open(context, found);
      unawaited(Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => ConversationDetailPage(conversation: found)),
      ));
    } catch (_) {
      // Offline or a failed read: the next tick tries again.
    } finally {
      _reading = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(automaticallyImplyLeading: false, leading: const Center(child: OmiBackButton.circled())),
      body: ListView(
        key: const Key('finished_capture_processing'),
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg),
        children: [
          const SizedBox(height: OmiSpacing.xxl),
          const Center(child: OmiSpinner()),
          SummaryWaitingNotice(
            title: context.l10n.processing,
            body: context.l10n.summaryTranscriptionPendingBody,
          ),
        ],
      ),
    );
  }
}
