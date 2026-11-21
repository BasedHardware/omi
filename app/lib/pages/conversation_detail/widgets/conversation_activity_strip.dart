import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/summary_generation.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// A server-side processing pass on the open conversation, under the tab row: a hairline progress
/// bar and one line saying so.
///
/// While the reader's own reprocess runs, the Summary tab's "Summarizing with …" state is the one
/// progress surface, so this draws only when another tab is on screen — a request started from the
/// Transcript tab (the ⋯ menu, the speaker refresh) still shows progress.
///
/// While the server reports the conversation as processing, the strip re-reads it every
/// [pollInterval] (at most [maxPolls] times) so the result replaces the strip without the reader
/// leaving and coming back. When the reads run out it says it is still working, with Try Again, and
/// reads again when the app comes back to the front (X12). On v3 it names the step, "Transcribing…"
/// then "Writing summary…"; the page's LiveConversationRefresher and the LiveSummarySection own
/// those reads, so the strip does not poll for them.
class ConversationActivityStrip extends StatefulWidget {
  const ConversationActivityStrip({
    super.key,
    this.pollInterval = const Duration(seconds: 5),
    this.maxPolls = 36,
    this.summaryTabVisible = true,
  });

  final Duration pollInterval;
  final int maxPolls;

  /// Whether the Summary tab — the reprocess's primary progress surface — is on screen.
  final bool summaryTabVisible;

  @override
  State<ConversationActivityStrip> createState() => _ConversationActivityStripState();
}

class _ConversationActivityStripState extends State<ConversationActivityStrip> with WidgetsBindingObserver {
  Timer? _poll;
  String? _pollingId;
  int _polls = 0;
  bool _polling = false;

  /// The reads ran out while the conversation was still being worked on.
  bool _exhausted = false;
  ConversationDetailProvider? _provider;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _poll?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _exhausted) _resume();
  }

  /// Try Again, or back in the front: read now and poll again with a fresh budget.
  void _resume() {
    final provider = _provider;
    final id = _pollingId;
    if (provider == null || id == null || !mounted) return;
    setState(() => _exhausted = false);
    _start(provider, id);
    unawaited(provider.refreshConversation());
  }

  void _syncPolling(ConversationDetailProvider provider, ServerConversation? conversation) {
    _provider = provider;
    final processingId =
        conversation != null && conversation.status == ConversationStatus.processing ? conversation.id : null;
    if (processingId == _pollingId) return;
    _poll?.cancel();
    _poll = null;
    _pollingId = processingId;
    _exhausted = false;
    if (processingId == null) return;
    _start(provider, processingId);
  }

  void _start(ConversationDetailProvider provider, String processingId) {
    _poll?.cancel();
    _polls = 0;
    _poll = Timer.periodic(widget.pollInterval, (timer) async {
      if (!mounted || provider.conversationOrNull?.id != processingId) {
        timer.cancel();
        return;
      }
      if (_polls >= widget.maxPolls) {
        timer.cancel();
        setState(() => _exhausted = true);
        return;
      }
      // One read at a time: a slow read is not overtaken by the next tick.
      if (_polling) return;
      _polling = true;
      _polls++;
      try {
        await provider.refreshConversation();
      } finally {
        _polling = false;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<ConversationDetailProvider>();
    final conversation = provider.conversationOrNull;
    final v3 = context.select<ConversationsV3Provider?, bool>((p) => p?.v3 ?? false);
    _syncPolling(provider, conversation);
    final tile = v3 ? conversation?.v3?.tileState : null;

    final l10n = context.l10n;
    final String? label;
    if (provider.isReprocessingOpenConversation && !widget.summaryTabVisible) {
      // Not on the tab that owns the primary progress surface: keep a global indicator so a
      // request started from this tab never runs invisibly.
      label = l10n.summarySummarizingWith(summarySourceName(provider, provider.reprocessingAppId, l10n));
    } else if (!provider.isReprocessingOpenConversation && tile == ConversationTileState.transcribing) {
      label = l10n.homeStepTranscribing;
    } else if (!provider.isReprocessingOpenConversation && tile == ConversationTileState.writing) {
      label = l10n.writingSummaryStatus;
    } else if (!provider.isReprocessingOpenConversation && conversation?.status == ConversationStatus.processing) {
      label = l10n.processingConversationProgress;
    } else {
      label = null;
    }

    if (label != null && _exhausted && !provider.isReprocessingOpenConversation) {
      // The reads ran out: no endless bar. Say it is still going, with Try Again (X12).
      return OmiPartialNotice(
        key: const Key('conversation_activity_paused'),
        message: l10n.stillWorkingOnIt,
        onRetry: _resume,
      );
    }

    return AnimatedSize(
      duration: const Duration(milliseconds: 200),
      alignment: Alignment.topCenter,
      child: label == null
          ? const SizedBox(width: double.infinity)
          : Semantics(
              key: const Key('conversation_activity_strip'),
              liveRegion: true,
              label: label,
              child: ExcludeSemantics(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    LinearProgressIndicator(
                      minHeight: 2,
                      color: OmiColors.textSecondary,
                      backgroundColor: Colors.transparent,
                    ),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, 0),
                      child: Text(label, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                    ),
                  ],
                ),
              ),
            ),
    );
  }
}
