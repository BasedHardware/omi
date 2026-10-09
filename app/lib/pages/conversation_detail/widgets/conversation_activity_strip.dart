import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Work on the open conversation that the reader is waiting for, under the tab row: a hairline
/// progress bar and one line saying what is happening ("Reprocessing conversation…"), for a
/// reprocess started from this page or a server-side processing pass. Nothing is drawn otherwise.
///
/// While the server reports the conversation as processing, the strip re-reads it every
/// [pollInterval] (at most [maxPolls] times) so the result replaces the strip without the reader
/// leaving and coming back.
class ConversationActivityStrip extends StatefulWidget {
  const ConversationActivityStrip({super.key, this.pollInterval = const Duration(seconds: 5), this.maxPolls = 36});

  final Duration pollInterval;
  final int maxPolls;

  @override
  State<ConversationActivityStrip> createState() => _ConversationActivityStripState();
}

class _ConversationActivityStripState extends State<ConversationActivityStrip> {
  Timer? _poll;
  String? _pollingId;
  int _polls = 0;
  bool _polling = false;

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  void _syncPolling(ConversationDetailProvider provider, ServerConversation? conversation) {
    final processingId =
        conversation != null && conversation.status == ConversationStatus.processing ? conversation.id : null;
    if (processingId == _pollingId) return;
    _poll?.cancel();
    _poll = null;
    _pollingId = processingId;
    _polls = 0;
    if (processingId == null) return;
    _poll = Timer.periodic(widget.pollInterval, (timer) async {
      if (!mounted || _polls >= widget.maxPolls || provider.conversationOrNull?.id != processingId) {
        timer.cancel();
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
    _syncPolling(provider, conversation);

    final l10n = context.l10n;
    final String? label;
    if (provider.isReprocessingOpenConversation) {
      label = l10n.reprocessingConversationProgress;
    } else if (conversation?.status == ConversationStatus.processing) {
      label = l10n.processingConversationProgress;
    } else {
      label = null;
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
