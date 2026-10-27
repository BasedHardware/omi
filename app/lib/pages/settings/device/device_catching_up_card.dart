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
  bool hasPending,
  bool hasUploaded,
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
  // Exactly the rows On the Way lists, so the card can never open an empty page:
  // terminal recordings belong to the bell, a lagging device twin is hidden, and
  // a drain's copied pieces fold into their source.
  final uploaded = wals.where((w) => w.status == WalStatus.uploaded).toList(growable: false);
  final rows = [...uploaded, ...SyncPendingWork.syncingOf(wals)];
  var onDeviceSeconds = 0;
  var onPhoneSeconds = 0;
  DateTime? start, end;
  final ids = <String>{};
  for (final w in rows) {
    if (w.conversationId case final id? when id.isNotEmpty) ids.add(id);
    if (w.seconds <= 0) continue;
    if (walIsOnDevice(w)) {
      onDeviceSeconds += w.seconds;
    } else if (w.status == WalStatus.miss) {
      // Recorded on the phone, waiting for its upload: the device card says
      // where the backlog sits instead of reading 0s while hours are queued.
      onPhoneSeconds += w.seconds;
    }
    if (w.timerStart <= 0) continue;
    // A recording time before the plausibility floor is a device clock that was
    // never set; the seconds still count, but the range must not stretch to it.
    if (!walTimerStartPlausible(w.timerStart)) {
      logImplausibleRecordingStart('catch_up_card', w.id, w.timerStart);
      continue;
    }
    final from = DateTime.fromMillisecondsSinceEpoch(w.timerStart * 1000);
    final to = from.add(Duration(seconds: w.seconds));
    if (start == null || from.isBefore(start)) start = from;
    if (end == null || to.isAfter(end)) end = to;
  }
  final targets = ids.toList()..sort();
  final result = (
    onDeviceSeconds: onDeviceSeconds,
    onPhoneSeconds: onPhoneSeconds,
    hasPending: rows.isNotEmpty,
    hasUploaded: uploaded.isNotEmpty,
    start: start,
    end: end,
    targetIds: targets.join('\n'),
  );
  _catchUpMemo[wals] = (wals.length, result);
  return result;
}

final Expando<(int, DeviceCatchUpLocal)> _catchUpMemo = Expando('deviceCatchUpLocal');

/// Local transfers and server work share a card, even after upload or before targets are known.
/// Progress is deliberately indeterminate: a device drain's pieces, virtual source timestamps and
/// shrinking on-device lengths make inventory arithmetic unreliable, so the card shows where the
/// work is, not how far along it is.
class DeviceCatchUpSummary {
  const DeviceCatchUpSummary({
    required this.status,
    this.start,
    this.end,
    this.targetIds = const {},
    this.targetTitles = const [],
  });

  static DeviceCatchUpSummary? from({
    required DeviceCatchUpLocal local,
    required bool serverProcessing,
    required String status,
    required List<PendingWorkItem> pending,
    required List<ServerConversation> conversations,
    required List<ServerConversation> processing,
  }) {
    if (!local.hasPending && !serverProcessing && pending.isEmpty && processing.isEmpty) return null;
    var start = local.start, end = local.end;
    final ids = {if (local.targetIds.isNotEmpty) ...local.targetIds.split('\n')};
    void include(DateTime? from, int seconds, String id) {
      if (from == null || seconds <= 0) return;
      from = from.toLocal();
      // The floor the card applies to WAL times also guards server-provided
      // starts, which inherit the same never-set device clock.
      if (!recordingStartPlausible(from)) {
        logImplausibleRecordingStart('catch_up_card', id, from.millisecondsSinceEpoch ~/ 1000);
        return;
      }
      final to = from.add(Duration(seconds: seconds));
      if (start == null || from.isBefore(start!)) start = from;
      if (end == null || to.isAfter(end!)) end = to;
    }

    for (final work in pending) {
      ids.addAll(work.conversationIds);
      include(work.startedAt, work.durationSeconds ?? 0, work.id);
    }
    for (final conversation in processing) {
      ids.add(conversation.id);
      include(conversation.startedAt, conversation.getDurationInSeconds(), conversation.id);
    }
    final titles = <String>[];
    for (final id in ids) {
      final conversation = [...conversations, ...processing].where((c) => c.id == id).firstOrNull;
      final title = conversation?.structured.title.trim() ?? '';
      if (title.isNotEmpty) titles.add(title);
    }
    return DeviceCatchUpSummary(
      status: status,
      start: start,
      end: end,
      targetIds: ids,
      targetTitles: titles,
    );
  }

  /// Where the work is right now, in On the Way's words.
  final String status;
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
    final dates = OmiDateFormat.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(l10n.deviceCatchingUp, style: OmiType.callout),
          const SizedBox(height: OmiSpacing.xxs),
          Text(
            summary.status,
            key: const Key('device_catching_up_status'),
            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
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
