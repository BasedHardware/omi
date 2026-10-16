import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/conversations/on_the_way_page.dart';
import 'package:omi/pages/conversations/sync_pending_work.dart';
import 'package:omi/pages/conversations/widgets/date_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// Home's one row for recordings that are not conversations yet: it sits in
/// Today, where the conversations will land, and opens the On the Way page.
///
/// Home used to go quiet the moment a conversation ended, and later grew a
/// full-width pipeline card for the same job. One row keeps the work visible
/// without a progress bar or an hour count above the fold: a long backlog says
/// "catching up" instead of how much is left.
///
/// The row also stands for conversations still processing and for server work the phone did not
/// start: Home draws no processing cards of its own, and slow work never reads as a problem.
class HomePendingRow extends StatelessWidget {
  const HomePendingRow({
    super.key,
    this.syncProvider,
    this.showTodayHeader = false,
    this.multiFileSync,
    this.pendingWork,
  });

  /// Injectable for tests and the visual audit; defaults to the app provider.
  final SyncProvider? syncProvider;

  /// Draws the Today header above the row, for a Home whose list has no Today yet.
  final bool showTodayHeader;

  /// Forwarded to the On the Way page's Sync Details link.
  final bool? multiFileSync;

  /// Injectable for tests; defaults to [PendingWorkStore.instance].
  final PendingWorkStore? pendingWork;

  /// Whether Home has anything on its way, by the same rule the row uses to draw itself.
  static bool hasWork(SyncProvider sync, PendingWorkStore store, ConversationProvider? conversations) =>
      SyncPendingWork.shouldShow(sync) ||
      (conversations?.processingConversations.isNotEmpty ?? false) ||
      store.pending.isNotEmpty;

  @override
  Widget build(BuildContext context) {
    final store = pendingWork ?? PendingWorkStore.instance;
    final conversations = context.watch<ConversationProvider?>();
    return ListenableBuilder(
      listenable: store,
      builder: (context, _) => Consumer<SyncProvider>(
        builder: (context, sync, child) {
          final p = syncProvider ?? sync;
          if (!hasWork(p, store, conversations)) return const SizedBox.shrink();
          final l = context.l10n;
          final title = SyncPendingWork.isLargeBacklog(p) ? l.homePendingCatchingUp : l.homePendingTitle;
          // Recordings say where they are; with none, what is left is conversations being processed.
          final subtitle = SyncPendingWork.shouldShow(p) ? SyncPendingWork.stageLabel(p, l) : l.processing;
          final now = DateTime.now();
          void open() => routeToPage(context, OnTheWayPage(syncProvider: syncProvider, multiFileSync: multiFileSync));
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              if (showTodayHeader) DateListItem(date: DateTime(now.year, now.month, now.day), isFirst: true),
              Padding(
                padding: const EdgeInsets.only(top: 8, left: 16, right: 16),
                child: Semantics(
                  button: true,
                  liveRegion: true,
                  label: '$title, $subtitle',
                  onTap: open,
                  excludeSemantics: true,
                  child: Material(
                    key: const Key('home_pending_row'),
                    color: OmiColors.surface1,
                    borderRadius: OmiRadius.xlAll,
                    child: InkWell(
                      borderRadius: OmiRadius.xlAll,
                      onTap: open,
                      child: Padding(
                        padding: const EdgeInsetsDirectional.fromSTEB(14, 14, 10, 14),
                        child: Row(
                          children: [
                            Container(
                              width: 36,
                              height: 36,
                              decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
                              alignment: Alignment.center,
                              child: const OmiSpinner(size: OmiSpinnerSize.small),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    title,
                                    style: Theme.of(context).textTheme.titleMedium,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                  const SizedBox(height: 3),
                                  Text(
                                    subtitle,
                                    style: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(width: 8),
                            Icon(Icons.chevron_right, color: OmiColors.textTertiary),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}
