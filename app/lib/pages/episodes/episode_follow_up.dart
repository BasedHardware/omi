import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Saves through the canonical Tasks provider/API. No second todo store.
class EpisodeFollowUp extends StatefulWidget {
  const EpisodeFollowUp({super.key, required this.episodeId, required this.text, required this.conversationId});
  final String episodeId;
  final String text;
  final String? conversationId;

  @override
  State<EpisodeFollowUp> createState() => _EpisodeFollowUpState();
}

class _EpisodeFollowUpState extends State<EpisodeFollowUp> {
  bool _pending = false;
  bool _saved = false;

  Future<void> _add() async {
    if (_pending || _saved || widget.conversationId == null || widget.episodeId.isEmpty) return;
    setState(() => _pending = true);
    // Stable across retries, reordering and page reopen. The server scopes this key to uid.
    final key = 'episode-follow-up:${sha256.convert(utf8.encode(jsonEncode([widget.episodeId, widget.text.trim()])))}';
    final task = await context
        .read<ActionItemsProvider>()
        .createActionItem(description: widget.text.trim(), conversationId: widget.conversationId, idempotencyKey: key);
    if (!mounted) return;
    setState(() {
      _pending = false;
      _saved = task != null;
    });
    if (task == null) OmiFeedback.error(context, context.l10n.somethingWentWrongTryAgain);
  }

  @override
  Widget build(BuildContext context) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
              child: Padding(
            padding: const EdgeInsets.symmetric(vertical: OmiSpacing.sm),
            child: Text(widget.text, style: OmiType.callout.copyWith(height: 1.4)),
          )),
          const SizedBox(width: OmiSpacing.xs),
          OmiIconButton.filled(
            key: ValueKey('episode_follow_up_add_${widget.text}'),
            label: _saved
                ? context.l10n.taskAddedToTasks
                : _pending
                    ? context.l10n.addingToTasks
                    : context.l10n.addToTasks,
            icon: _pending
                ? const OmiSpinner(size: OmiSpinnerSize.small)
                : Icon(_saved ? Icons.check_rounded : Icons.add_rounded),
            fillColor: OmiColors.surface2,
            onPressed: _pending || _saved || widget.conversationId == null || widget.episodeId.isEmpty ? null : _add,
          ),
        ],
      );
}
