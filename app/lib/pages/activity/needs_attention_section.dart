import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/pages/chat/widgets/content_blocks/conversation_link_blocks.dart';
import 'package:omi/pages/conversations/recording_blocks.dart';
import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/pages/conversations/sync_pending_work.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Work that could not finish, at the top of Activity: conversations the server gave up summarizing
/// (with Try Again) and recordings that could not be processed (opening Offline Sync, which owns
/// their retry). Home never shows these; the bell's warning dot points here.
///
/// Capture problems live here too, read from the capture wedge monitor: a pendant that stopped
/// sending audio (Home has no banner, so the bell's dot points here), a full phone disk pausing
/// recordings, and an upload stalled long enough to need attention. The storage and upload rows
/// open Offline Sync, which owns storage management and retry; the link row reconnects in place.
class NeedsAttentionSection extends StatelessWidget {
  const NeedsAttentionSection({
    super.key,
    required this.store,
    this.syncProvider,
    this.captureMonitor,
    this.openConversation,
  });

  final PendingWorkStore store;

  /// Injectable for tests; defaults to the app provider when one is in scope.
  final SyncProvider? syncProvider;

  /// Injectable for tests; defaults to [CaptureWedgeMonitor.instance].
  final CaptureWedgeMonitor? captureMonitor;

  /// Injectable for tests; defaults to opening the conversation detail page.
  final Future<void> Function(BuildContext context, String conversationId)? openConversation;

  /// Whether the section draws anything for this state.
  static bool hasContent(PendingWorkStore store, SyncProvider? sync, [CaptureWedgeMonitor? monitor]) =>
      store.attention.isNotEmpty || _recordingCount(sync) > 0 || monitor?.hasCaptureAttention == true;

  static int _recordingCount(SyncProvider? sync) =>
      sync == null ? 0 : groupRecordingBlocks(SyncPendingWork.attention(sync)).length;

  @override
  Widget build(BuildContext context) {
    final sync = syncProvider ?? context.watch<SyncProvider?>();
    final monitor = captureMonitor ?? CaptureWedgeMonitor.instance;
    return ListenableBuilder(
      listenable: Listenable.merge([store, monitor]),
      builder: (context, _) {
        if (!hasContent(store, sync, monitor)) return const SizedBox.shrink();
        final l = context.l10n;
        final dates = OmiDateFormat.of(context);
        final recordings = _recordingCount(sync);
        final storage = monitor.storageAtRisk;
        final upload = monitor.uploadStall;
        final acute = monitor.acuteEpisode;
        final ingressFailure = acute?.trigger == CaptureWedgeMonitor.triggerIngressRecoveryFailed;
        // "Still recording on your Omi" only where the pendant is off the link and keeps audio on
        // the device. A pendant that is connected but silent may be discarding live frames, and an
        // exhausted ingress recovery proves ingress, not durability (INV-CAP-1): no claim for either.
        final retentionPlausible =
            acute != null && !ingressFailure && acute.trigger != CaptureWedgeMonitor.triggerConnectedNoBytes;
        final retryable = store.attention.where((i) => i.retryable && i.retryState == AttentionRetryState.none);
        return Column(
          key: const Key('activity_needs_attention'),
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(OmiSpacing.xxs, OmiSpacing.md, 0, OmiSpacing.xxs),
              child: Row(
                children: [
                  Expanded(
                    child: Semantics(
                      header: true,
                      child: Text(
                        l.activityNeedsAttention.toUpperCase(),
                        // The same header as Activity's day groups: the row icons carry the warning.
                        style: OmiType.footnote
                            .copyWith(fontWeight: FontWeight.w600, color: OmiColors.textSecondary, letterSpacing: 0.4),
                      ),
                    ),
                  ),
                  if (retryable.length > 1)
                    OmiButton.tertiary(
                      key: const Key('activity_retry_all'),
                      label: l.activityRetryAll,
                      onPressed: store.retryAll,
                    ),
                ],
              ),
            ),
            Material(
              color: OmiColors.surface1,
              borderRadius: OmiRadius.xlAll,
              clipBehavior: Clip.antiAlias,
              child: Column(
                children: [
                  for (final (index, item) in store.attention.indexed) ...[
                    if (index > 0) Divider(height: 1, thickness: 1, indent: 64, color: OmiColors.surface2),
                    _AttentionRow(
                      key: ValueKey('activity_attention_${item.id}'),
                      title: item.title ?? l.attentionSummaryFailed,
                      subtitle: [
                        if (item.title != null) l.attentionSummaryFailed,
                        if (item.startedAt != null) dates.time(item.startedAt!.toLocal()),
                      ].join(' · '),
                      busy: item.retryState == AttentionRetryState.inProgress,
                      onRetry: item.retryable && item.retryState == AttentionRetryState.none
                          ? () => store.retry(item)
                          : null,
                      onTap: item.conversationId == null
                          ? null
                          : () => (openConversation ?? _openConversation)(context, item.conversationId!),
                    ),
                  ],
                  if (recordings > 0) ...[
                    if (store.attention.isNotEmpty)
                      Divider(height: 1, thickness: 1, indent: 64, color: OmiColors.surface2),
                    _AttentionRow(
                      key: const Key('activity_attention_recordings'),
                      title: l.syncCardNeedsAttention(recordings),
                      subtitle: l.syncDetailsTitle,
                      busy: false,
                      onRetry: null,
                      onTap: () => openOfflineSyncDetails(context, sync!),
                    ),
                  ],
                  if (acute != null) ...[
                    if (store.attention.isNotEmpty || recordings > 0)
                      Divider(height: 1, thickness: 1, indent: 64, color: OmiColors.surface2),
                    // The acute link episode, the one capture problem with an in-place fix:
                    // tapping reconnects (the same retry as the live page), it never navigates.
                    // An exhausted ingress recovery has no Dart retry and no audio-saved claim
                    // (INV-CAP-1); its row explains instead.
                    _CaptureAttentionRow(
                      key: const Key('activity_attention_capture_link'),
                      icon: Icons.bluetooth_disabled,
                      title: ingressFailure ? l.captureIngressNeedsReconnect : l.captureRecoveryBannerTitle,
                      subtitle: retentionPlausible ? l.activityAttentionLinkStalledSubtitle : '',
                      actionLabel: ingressFailure ? null : l.reconnect,
                      onTap: ingressFailure
                          ? () => LiveCaptureCard.showDetails(context,
                              title: l.captureIngressNeedsReconnect,
                              explanation: l.captureIngressNeedsReconnectExplanation)
                          : () {
                              monitor.onRecoveryActioned(surface: 'activity');
                              monitor.retryVisibleEpisode();
                            },
                    ),
                  ],
                  if (storage != null) ...[
                    if (store.attention.isNotEmpty || recordings > 0 || acute != null)
                      Divider(height: 1, thickness: 1, indent: 64, color: OmiColors.surface2),
                    _CaptureAttentionRow(
                      key: const Key('activity_attention_storage'),
                      icon: Icons.sd_storage_outlined,
                      // blockedCount counts admission attempts, not recordings:
                      // one recording's repeated retries must not read as many
                      // paused recordings, so the row names no count. The title
                      // names the condition the retention risk proved: a failed
                      // free-space probe is not a full disk.
                      title: storage.reason == 'disk_space_unknown'
                          ? l.activityAttentionStorageUnknownTitle
                          : l.capturePhoneStorageFull,
                      subtitle: l.activityAttentionStorageSubtitle,
                      onTap: sync == null ? null : () => openOfflineSyncDetails(context, sync, phoneLocal: true),
                    ),
                  ],
                  if (upload != null) ...[
                    if (store.attention.isNotEmpty || recordings > 0 || acute != null || storage != null)
                      Divider(height: 1, thickness: 1, indent: 64, color: OmiColors.surface2),
                    _CaptureAttentionRow(
                      key: const Key('activity_attention_upload_stalled'),
                      icon: Icons.cloud_upload_outlined,
                      title: l.activityAttentionUploadStalledTitle,
                      subtitle: [
                        l.activityAttentionUploadRecordings(upload.pendingCount),
                        // The kept-audio length, compact: "5 recordings waiting · 47m".
                        if (upload.pendingSeconds > 0) OmiDuration.compact(upload.pendingSeconds, l),
                      ].join(' · '),
                      onTap: sync == null ? null : () => openOfflineSyncDetails(context, sync, phoneLocal: true),
                    ),
                  ],
                ],
              ),
            ),
          ],
        );
      },
    );
  }

  static Future<void> _openConversation(BuildContext context, String conversationId) async {
    await openChatBlockConversation(context, conversationId: conversationId);
  }
}

class _AttentionRow extends StatelessWidget {
  const _AttentionRow({
    super.key,
    required this.title,
    required this.subtitle,
    required this.busy,
    required this.onRetry,
    required this.onTap,
  });

  final String title;
  final String subtitle;
  final bool busy;
  final VoidCallback? onRetry;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(14, 14, 10, 14),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
              alignment: Alignment.center,
              child: Icon(Icons.warning_amber_rounded, size: 18, color: OmiColors.warning),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: OmiType.body, maxLines: 2, overflow: TextOverflow.ellipsis),
                  if (subtitle.isNotEmpty) ...[
                    const SizedBox(height: 3),
                    Text(subtitle, style: OmiType.subhead.copyWith(color: OmiColors.textTertiary)),
                  ],
                ],
              ),
            ),
            if (busy)
              const Padding(
                padding: EdgeInsetsDirectional.only(start: OmiSpacing.xs, end: OmiSpacing.xs),
                child: OmiSpinner(size: OmiSpinnerSize.small),
              )
            else if (onRetry != null)
              OmiButton.secondary(
                label: context.l10n.tryAgain,
                onPressed: onRetry,
                size: OmiButtonSize.compact,
              )
            else if (onTap != null)
              Icon(Icons.chevron_right, color: OmiColors.textTertiary),
          ],
        ),
      ),
    );
  }
}

/// A capture problem row, drawn like the summary-failure rows above (settings style, no button):
/// a neutral badge whose amber glyph names the problem (a link, a disk, an upload), the title says
/// what is wrong, and a chevron says the row opens Offline Sync. The one exception is an in-place
/// fix ([actionLabel]): the trailing slot names it in plain text, since a chevron would promise a
/// page that does not open.
class _CaptureAttentionRow extends StatelessWidget {
  const _CaptureAttentionRow({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    this.actionLabel,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;

  /// Names an in-place fix ("Reconnect") in the trailing slot instead of a chevron.
  final String? actionLabel;

  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(14, 14, 10, 14),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
              alignment: Alignment.center,
              child: ExcludeSemantics(child: Icon(icon, size: 18, color: OmiColors.warning)),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: OmiType.body, maxLines: 2, overflow: TextOverflow.ellipsis),
                  if (subtitle.isNotEmpty) ...[
                    const SizedBox(height: 3),
                    Text(subtitle, style: OmiType.subhead.copyWith(color: OmiColors.textTertiary)),
                  ],
                ],
              ),
            ),
            if (onTap != null && actionLabel != null)
              OmiButton.tertiary(label: actionLabel!, onPressed: onTap, size: OmiButtonSize.compact)
            else if (onTap != null)
              Icon(Icons.chevron_right, color: OmiColors.textTertiary),
          ],
        ),
      ),
    );
  }
}
