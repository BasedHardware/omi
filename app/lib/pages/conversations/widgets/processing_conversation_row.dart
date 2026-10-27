import 'package:flutter/material.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// A conversation that just ended and is still processing, on Home under the live row: a quiet
/// card with a turning ring, "Processing…" until its title arrives, and when it started. The
/// placeholder the app adds the moment the person ends a conversation is replaced by the server's
/// row, then by the finished conversation.
class ProcessingConversationRow extends StatelessWidget {
  const ProcessingConversationRow({super.key, required this.conversation});

  final ServerConversation conversation;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final title = conversation.structured.title.trim();
    final started = conversation.startedAt ?? conversation.createdAt;
    final time = MaterialLocalizations.of(context).formatTimeOfDay(TimeOfDay.fromDateTime(started.toLocal()));
    return Padding(
      padding: const EdgeInsets.only(top: 8, left: 16, right: 16),
      child: Semantics(
        label: '${title.isEmpty ? l10n.wrappedProcessingDefault : title}, $time',
        excludeSemantics: true,
        child: Container(
          key: const Key('home_processing_row'),
          padding: const EdgeInsetsDirectional.fromSTEB(14, 14, 14, 14),
          decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
          child: Row(
            children: [
              Container(
                width: 36,
                height: 36,
                alignment: Alignment.center,
                decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
                child: const OmiActivityRing(active: true, diameter: 18, child: SizedBox.shrink()),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title.isEmpty ? l10n.wrappedProcessingDefault : title,
                      style: Theme.of(context).textTheme.titleMedium,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 3),
                    Text(time, style: OmiType.subhead.copyWith(color: OmiColors.textTertiary)),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
