import 'dart:math';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/pages/conversations/sync_pending_work.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/sync/offline_sync_amounts.dart';

/// One snapshot shared by the device stats and the Catching up tile. Read the WAL inventory once,
/// outside capture/episode listeners, so streaming metrics never rescan recording history.
typedef DeviceCatchUpLocal = ({
  int onDeviceSeconds,
  int onPhoneSeconds,
  int pendingSeconds,
  bool hasPending,
  bool hasUploaded,
  DateTime? start,
  DateTime? end,
  String targetIds,
});

DeviceCatchUpLocal deviceCatchUpLocal(List<Wal> wals, {DateTime? now}) {
  final nowSeconds = (now ?? DateTime.now()).millisecondsSinceEpoch ~/ 1000;
  final minute = nowSeconds ~/ 60;
  // Sync progress notifies with the same list instance (the provider swaps it on
  // status changes), so an identity+length memo keeps a per-chunk tick from
  // rescanning recording history on the UI isolate.
  final memo = _catchUpMemo[wals];
  if (memo != null && memo.$1 == wals.length && memo.$2 == minute) return memo.$3;
  // Exactly the rows On the Way lists, so the card can never open an empty page:
  // terminal recordings belong to the bell, a lagging device twin is hidden, and
  // a drain's copied pieces fold into their source.
  final uploaded = wals.where((w) => w.status == WalStatus.uploaded).toList(growable: false);
  final rows = [...uploaded, ...SyncPendingWork.syncingOf(wals)];
  var onDeviceSeconds = 0;
  var onPhoneSeconds = 0;
  var pendingSeconds = 0;
  final spans = <(DateTime, DateTime)>[];
  final ids = <String>{};
  for (final w in rows) {
    if (w.conversationId case final id? when id.isNotEmpty) ids.add(id);
    if (w.seconds <= 0) continue;
    pendingSeconds += w.seconds;
    if (walIsOnDevice(w)) {
      onDeviceSeconds += w.seconds;
    } else if (w.status == WalStatus.miss) {
      // Recorded on the phone, waiting for its upload: the device card says
      // where the backlog sits instead of reading 0s while hours are queued.
      onPhoneSeconds += w.seconds;
    }
    if (w.timerStart <= 0) continue;
    // Historical handles retain custody/counts but must be confirmed pending
    // before they can claim a capture range in Right now.
    if (w.status == WalStatus.uploaded &&
        w.uploadedAt < nowSeconds - 86400 &&
        w.jobPendingConfirmedAt < nowSeconds - 300) {
      continue;
    }
    // A recording time before the plausibility floor is a device clock that was
    // never set; the seconds still count, but the range must not stretch to it.
    if (!walTimerStartPlausible(w.timerStart)) {
      logImplausibleRecordingStart('catch_up_card', w.id, w.timerStart);
      continue;
    }
    final from = DateTime.fromMillisecondsSinceEpoch(w.timerStart * 1000);
    final to = from.add(Duration(seconds: w.seconds));
    spans.add((from, to));
  }
  final (start, end) = pendingCatchUpSpan(spans);
  final targets = ids.toList()..sort();
  final result = (
    onDeviceSeconds: onDeviceSeconds,
    onPhoneSeconds: onPhoneSeconds,
    pendingSeconds: pendingSeconds,
    hasPending: rows.isNotEmpty,
    hasUploaded: uploaded.isNotEmpty,
    start: start,
    end: end,
    targetIds: targets.join('\n'),
  );
  _catchUpMemo[wals] = (wals.length, minute, result);
  return result;
}

final Expando<(int, int, DeviceCatchUpLocal)> _catchUpMemo = Expando('deviceCatchUpLocal');

/// One contiguous pending run on the most recent pending day. Inventory and
/// target totals still include historical work; a gap is never called audio.
(DateTime?, DateTime?) pendingCatchUpSpan(List<(DateTime, DateTime)> spans) {
  if (spans.isEmpty) return (null, null);
  spans.sort((a, b) => a.$2.compareTo(b.$2));
  final end = spans.last.$2;
  final midnight = DateTime(end.year, end.month, end.day);
  var start = spans.last.$1.isBefore(midnight) ? midnight : spans.last.$1;
  for (final span in spans.reversed.skip(1)) {
    if (span.$2.isBefore(midnight) || span.$2.isBefore(start.subtract(const Duration(minutes: 2)))) break;
    if (span.$1.isBefore(start)) start = span.$1.isBefore(midnight) ? midnight : span.$1;
  }
  return (start, end);
}

/// Local transfers and server work share one catch-up figure, even after upload or before targets
/// are known. The stat tile shows only how much audio is still on its way; On the Way says where.
class DeviceCatchUpSummary {
  const DeviceCatchUpSummary({
    required this.status,
    this.seconds = 0,
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
    final spans = <(DateTime, DateTime)>[
      if (local.start != null && local.end != null) (local.start!, local.end!),
    ];
    final ids = {if (local.targetIds.isNotEmpty) ...local.targetIds.split('\n')};
    // The same audio On the Way totals: a processing conversation whose recordings are still
    // listed locally is counted once, by its recordings, and a server sync job the phone is
    // running itself is already covered by them.
    var seconds = local.pendingSeconds;
    final processingIds = {for (final c in processing) c.id};
    for (final conversation in processing) {
      if (!ids.contains(conversation.id)) seconds += max(0, conversation.getDurationInSeconds());
    }
    final phoneSyncing = local.hasPending || serverProcessing;
    for (final work in pending) {
      if (work.conversationIds.any(processingIds.contains)) continue;
      if (work.kind == 'sync_job' && phoneSyncing) continue;
      seconds += max(0, work.durationSeconds ?? 0);
    }
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
      spans.add((from, to));
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
    final (start, end) = pendingCatchUpSpan(spans);
    return DeviceCatchUpSummary(
      status: status,
      seconds: seconds,
      start: start,
      end: end,
      targetIds: ids,
      targetTitles: titles,
    );
  }

  /// Where the work is right now, in On the Way's words.
  final String status;

  /// Audio still catching up, in seconds: the stat tile's value.
  final int seconds;
  final DateTime? start;
  final DateTime? end;
  final Set<String> targetIds;
  final List<String> targetTitles;
}
