import 'package:flutter/material.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/pages/conversations/home_rows.dart';
import 'package:omi/pages/episodes/episode_page.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// A conversation or episode that just ended and is still processing, on Home under the live row:
/// the same row in its middle state, a turning ring and "Writing notes… · 1h 36m". When several
/// recordings in a row are processing, the row says how many it stands for. It opens the same
/// page the finished row will. The placeholder the app adds the moment the person ends a
/// conversation is replaced by the server's row, then by the finished row.
class ProcessingConversationRow extends StatelessWidget {
  const ProcessingConversationRow({
    super.key,
    required this.conversation,
    this.episode,
    this.step = HomeStep.writingNotes,
    this.count = 1,
  });

  final ServerConversation conversation;

  /// The episode this row stands for; a lone conversation has none yet.
  final Episode? episode;

  /// The current processing step shown in the subtitle.
  final HomeStep step;

  /// How many recordings this row stands for; a count above one is shown in the subtitle.
  final int count;

  void _open(BuildContext context) {
    OmiHaptics.selection();
    final started = conversation.startedAt ?? conversation.createdAt;
    routeToPage(
      context,
      EpisodePage(
        episode: episode ??
            Episode(
              id: '',
              live: false,
              startedAt: started,
              lastActivityAt: conversation.finishedAt ?? DateTime.now(),
              conversationIds: [conversation.id],
              members: [conversation],
              title: conversation.structured.title,
            ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final started = conversation.startedAt ?? conversation.createdAt;
    final seconds = conversation.finishedAt?.difference(started).inSeconds ?? 0;
    // A run's span is wall-clock, not recording time, so a run shows its count instead.
    final size =
        count > 1 ? l10n.homeRecordingsCount(count) : (seconds > 0 ? OmiDuration.compact(seconds, l10n) : null);
    final meta = [
      if (step == HomeStep.transcribing) l10n.homeStepTranscribing,
      if (step == HomeStep.writingNotes) l10n.episodeWritingNotes,
      if (size != null) size,
    ].join(' · ');
    final shownTitle = l10n.wrappedProcessingDefault;
    return Padding(
      padding: const EdgeInsets.only(top: 8, left: 16, right: 16),
      child: Semantics(
        button: true,
        label: '$shownTitle, $meta',
        excludeSemantics: true,
        onTap: () => _open(context),
        child: Material(
          key: const Key('home_processing_row'),
          color: OmiColors.surface1,
          shape: const RoundedRectangleBorder(borderRadius: OmiRadius.xlAll),
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: () => _open(context),
            child: Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(14, 14, 10, 14),
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
                          shownTitle,
                          style: Theme.of(context).textTheme.titleMedium,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: 3),
                        Text(
                          meta,
                          style: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                  Icon(Icons.chevron_right_rounded, color: OmiColors.textDisabled),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
