import 'package:flutter/material.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/pages/conversations/sync_pending_work.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/sync/offline_sync_amounts.dart';

/// One snapshot shared by the device stats and the catch-up card. Read the WAL inventory once,
/// outside capture/episode listeners, so streaming metrics never rescan recording history.
typedef DeviceCatchUpLocal = ({
  int onDeviceSeconds,
  int onPhoneSeconds,
  int totalSeconds,
  int movedSeconds,
  bool hasPending,
  DateTime? start,
  DateTime? end,
  String targetIds,
});

DeviceCatchUpLocal deviceCatchUpLocal(List<Wal> wals) {
  // Sync progress notifies with the same list instance (the provider swaps it on
  // status changes), so an identity+length memo keeps a per-chunk tick from
  // rescanning recording history on the UI isolate.
  final memo = _catchUpMemo[wals];
  if (memo != null && memo.$1 == wals.length) return memo.$2;
  final hidden = SyncPendingWork.hiddenDeviceTwinIds(wals);
  // The same rows On the Way lists: terminal recordings belong to the bell, and
  // a hidden twin is bookkeeping lag, not audio waiting anywhere. A drain's
  // copied pieces fold into their source exactly as On the Way groups them, so
  // they never count twice: the source stands for the whole recording, and each
  // piece counts once as audio that already left the device.
  final sources = wals
      .where((w) => walIsOnDevice(w) && SyncPendingWork.isPendingWal(w) && !hidden.contains(w.id))
      .toList(growable: false);
  final copiedBySource = <String, int>{};
  DateTime? start, end;
  final ids = <String>{};
  var onDeviceSeconds = 0, onPhoneSeconds = 0, phoneRecordedSeconds = 0, processingSeconds = 0;
  var hasPending = false;
  for (final w in wals) {
    final uploadedRow = w.status == WalStatus.uploaded;
    final pendingRow = !uploadedRow && SyncPendingWork.isPendingWal(w) && !hidden.contains(w.id);
    if (!uploadedRow && !pendingRow) continue;
    hasPending = true;
    if (w.conversationId case final id? when id.isNotEmpty) ids.add(id);
    final seconds = w.seconds > 0 ? w.seconds : 0;
    final source = uploadedRow || !walIsOnDevice(w) ? SyncPendingWork.sourceOfPiece(w, sources) : null;
    if (source != null) {
      // A piece of a visible source: moved audio inside the source's own total.
      copiedBySource[source.id] = (copiedBySource[source.id] ?? 0) + seconds;
      continue;
    }
    if (w.timerStart > 0 && seconds > 0) {
      final from = DateTime.fromMillisecondsSinceEpoch(w.timerStart * 1000);
      final to = from.add(Duration(seconds: seconds));
      if (start == null || from.isBefore(start)) start = from;
      if (end == null || to.isAfter(end)) end = to;
    }
    if (uploadedRow) {
      processingSeconds += seconds;
    } else if (walIsOnDevice(w)) {
      onDeviceSeconds += seconds;
    } else if (w.originalStorage != null && w.originalStorage != WalStorage.disk) {
      onPhoneSeconds += seconds;
    } else {
      phoneRecordedSeconds += seconds;
    }
  }
  // Never claim more moved audio than the source recording holds.
  var copiedSeconds = 0;
  for (final source in sources) {
    final copied = copiedBySource[source.id] ?? 0;
    if (copied <= 0) continue;
    final length = source.seconds > 0 ? source.seconds : 0;
    copiedSeconds += length == 0 || copied < length ? copied : length;
  }
  final targets = ids.toList()..sort();
  final result = (
    onDeviceSeconds: onDeviceSeconds,
    onPhoneSeconds: onPhoneSeconds + phoneRecordedSeconds,
    totalSeconds: onDeviceSeconds + onPhoneSeconds + phoneRecordedSeconds + processingSeconds,
    // Only audio that left device storage moves the bar: pieces copied or
    // uploaded from a device. Phone-recorded audio is waiting, not moved.
    movedSeconds: onPhoneSeconds + processingSeconds + copiedSeconds,
    hasPending: hasPending,
    start: start,
    end: end,
    targetIds: targets.join('\n'),
  );
  _catchUpMemo[wals] = (wals.length, result);
  return result;
}

final Expando<(int, DeviceCatchUpLocal)> _catchUpMemo = Expando('deviceCatchUpLocal');

/// Local transfers and server work share a card, even after upload or before targets are known.
/// Server totals can overlap local WALs, so they are never added to the local transfer denominator.
class DeviceCatchUpSummary {
  const DeviceCatchUpSummary({
    this.progress,
    this.start,
    this.end,
    this.targetIds = const {},
    this.targetTitles = const [],
  });

  static DeviceCatchUpSummary? from({
    required DeviceCatchUpLocal local,
    required bool serverProcessing,
    required List<PendingWorkItem> pending,
    required List<ServerConversation> conversations,
    required List<ServerConversation> processing,
  }) {
    if (!local.hasPending && !serverProcessing && pending.isEmpty && processing.isEmpty) return null;
    var start = local.start, end = local.end;
    final ids = {if (local.targetIds.isNotEmpty) ...local.targetIds.split('\n')};
    void include(DateTime? from, int seconds) {
      if (from == null || seconds <= 0) return;
      from = from.toLocal();
      final to = from.add(Duration(seconds: seconds));
      if (start == null || from.isBefore(start!)) start = from;
      if (end == null || to.isAfter(end!)) end = to;
    }

    for (final work in pending) {
      ids.addAll(work.conversationIds);
      include(work.startedAt, work.durationSeconds ?? 0);
    }
    for (final conversation in processing) {
      ids.add(conversation.id);
      include(conversation.startedAt, conversation.getDurationInSeconds());
    }
    final titles = <String>[];
    for (final id in ids) {
      final conversation = [...conversations, ...processing].where((c) => c.id == id).firstOrNull;
      final title = conversation?.structured.title.trim() ?? '';
      if (title.isNotEmpty) titles.add(title);
    }
    return DeviceCatchUpSummary(
      // Transfer completion does not mean transcription is done, and server-only
      // work has no measured local total: both stay indeterminate. Any forward-
      // moving local audio — on the device or already on the phone — is measured.
      progress: local.hasPending && local.onDeviceSeconds + local.onPhoneSeconds > 0 && local.totalSeconds > 0
          ? (doneSeconds: local.movedSeconds, totalSeconds: local.totalSeconds)
          : null,
      start: start,
      end: end,
      targetIds: ids,
      targetTitles: titles,
    );
  }

  final ({int doneSeconds, int totalSeconds})? progress;
  final DateTime? start;
  final DateTime? end;
  final Set<String> targetIds;
  final List<String> targetTitles;
}

class DeviceCatchingUpCard extends StatelessWidget {
  const DeviceCatchingUpCard({super.key, required this.summary, this.onOpen});

  final DeviceCatchUpSummary summary;
  final VoidCallback? onOpen;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final progress = summary.progress;
    final dates = OmiDateFormat.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(l10n.deviceCatchingUp, style: OmiType.callout),
          const SizedBox(height: OmiSpacing.xxs),
          Text(
            progress == null
                ? l10n.processing
                : l10n.deviceCatchingUpProgress(
                    (progress.doneSeconds / 60).floor(), (progress.totalSeconds / 60).ceil()),
            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
          ),
          const SizedBox(height: OmiSpacing.xs),
          ClipRRect(
            borderRadius: OmiRadius.pillAll,
            child: LinearProgressIndicator(
              value: progress == null || progress.totalSeconds <= 0
                  ? null
                  : (progress.doneSeconds / progress.totalSeconds).clamp(0.0, 1.0),
              minHeight: 6,
              backgroundColor: OmiColors.surface2,
              color: OmiColors.accent,
            ),
          ),
          if (summary.start != null && summary.end != null) ...[
            const SizedBox(height: OmiSpacing.xs),
            Text(
              '${dates.dayHeader(summary.start!)} · ${dates.timeRange(summary.start!, summary.end!)}',
              key: const Key('device_catching_up_span'),
              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
            ),
          ],
          if (summary.targetIds.isNotEmpty) ...[
            const SizedBox(height: OmiSpacing.xs),
            Text(
              [l10n.conversationCount(summary.targetIds.length), ...summary.targetTitles].join(' · '),
              key: const Key('device_catching_up_targets'),
              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
            ),
          ],
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: TextButton(
              key: const Key('device_catching_up_on_the_way'),
              onPressed: onOpen,
              child: Text(l10n.onTheWayTitle),
            ),
          ),
        ],
      ),
    );
  }
}
