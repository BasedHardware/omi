import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/recording_blocks.dart';
import 'package:omi/pages/conversations/sync_pending_work.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/sync/offline_sync_amounts.dart';

/// Recordings on their way to becoming conversations, opened from the device's Catching up
/// tile. A line on how it gets there, then one row per local day with that day's totals and a
/// quiet status. Failures recover on their own and never appear as rows here.
class OnTheWayPage extends StatefulWidget {
  const OnTheWayPage({super.key, this.syncProvider, this.multiFileSync, this.clock, this.pendingWork});

  /// Injectable for tests and the visual audit; defaults to the app provider.
  final SyncProvider? syncProvider;

  /// Injectable Sync Details routing for tests and the visual audit.
  final bool? multiFileSync;

  /// Injectable "now" for tests and the visual audit: which day is Today.
  final DateTime Function()? clock;

  /// Server work the device's Catching up tile also stands for. Injectable for tests; defaults to
  /// [PendingWorkStore.instance].
  final PendingWorkStore? pendingWork;

  @override
  State<OnTheWayPage> createState() => _OnTheWayPageState();
}

/// Listens to server work and reads the inventory.
mixin _PendingWorkListener<T extends StatefulWidget> on State<T> {
  PendingWorkStore get store;

  @override
  void initState() {
    super.initState();
    store.addListener(_onPendingWork);
  }

  @override
  void dispose() {
    store.removeListener(_onPendingWork);
    super.dispose();
  }

  void _onPendingWork() {
    if (mounted) setState(() {});
  }

  OmiDateFormat dateFormat(BuildContext context, DateTime Function()? clock) => OmiDateFormat(
        locale: Localizations.localeOf(context),
        use24HourFormat: MediaQuery.maybeAlwaysUse24HourFormatOf(context) ?? false,
        l10n: context.l10n,
        clock: clock,
      );
}

class _OnTheWayPageState extends State<OnTheWayPage> with _PendingWorkListener {
  @override
  late final PendingWorkStore store = widget.pendingWork ?? PendingWorkStore.instance;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final online = context.select<ConnectivityProvider?, bool>((c) => c?.isConnected ?? true);
    return Consumer<SyncProvider>(
      builder: (context, sync, child) {
        final p = widget.syncProvider ?? sync;
        final processing = context.watch<ConversationProvider?>()?.processingConversations ?? const [];
        final work = _PendingWork.collect(p, processing, store.pending, l);
        // Recordings that failed or were refused recover without the user; they are not rows
        // here, but they keep the page from claiming everything is synced.
        final quiet = p.needsAttentionWalsCount > 0 || p.terminallyFailedWalsCount > 0;
        final refusals = p.refusalSummary;

        final Widget body;
        if (work.isEmpty && !quiet) {
          body = OmiEmptyState(icon: Icons.check_circle_outline, title: l.allRecordingsSynced);
        } else {
          final dates = dateFormat(context, widget.clock);
          final days = _groupByDay(work.dated);
          final statuses = _dayStatuses(days, work.undated, l);
          body = ListView(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.xxl),
            children: [
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxs),
                child: Text(
                  online ? l.onTheWayUploadsByItself : l.onTheWayUploadsWhenOnline,
                  style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                ),
              ),
              if (work.status != null) ...[
                const SizedBox(height: OmiSpacing.xs),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxs),
                  child: Text(work.status!.label, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                ),
              ],
              const SizedBox(height: OmiSpacing.lg),
              // Only something the user can actually fix earns a line, and only one.
              if (refusals.userActionCanHelp && refusals.count > 0) ...[
                OmiSettingsGroup(children: [
                  OmiSettingsRow(
                    key: const Key('on_the_way_user_action'),
                    title: l.syncCardNeedsAttention(refusals.count),
                    onTap: () => openOfflineSyncDetails(context, p, multiFileSync: widget.multiFileSync),
                  ),
                ]),
                const SizedBox(height: OmiSpacing.lg),
              ],
              if (days.isNotEmpty || work.undatedRecordings.isNotEmpty)
                OmiSettingsGroup(
                  key: const Key('on_the_way_days'),
                  children: [
                    for (final day in days)
                      _DayRow(
                        key: Key('on_the_way_day_${_dayKey(day.day)}'),
                        title: dates.dayHeader(day.day),
                        subtitle: _totals(day.items, l),
                        status: statuses[day.day] ?? '',
                      ),
                    if (work.undatedRecordings.isNotEmpty)
                      _DayRow(
                        key: const Key('on_the_way_day_undated'),
                        title: l.onTheWayNoDate,
                        subtitle: _totals(work.undatedRecordings, l),
                        status: statuses[null] ?? '',
                      ),
                  ],
                ),
              Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, 0),
                child: Text(
                  l.onTheWayFootnote,
                  key: const Key('on_the_way_footnote'),
                  style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                ),
              ),
            ],
          );
        }
        return Scaffold(
          appBar: AppBar(leading: const OmiBackButton(), title: Text(l.onTheWayTitle)),
          body: body,
        );
      },
    );
  }

  /// Uploads go oldest first (live capture aside), so the oldest day still waiting is Next and
  /// the rest are Queued; a day moving now is Uploading, and a day whose audio has all landed is
  /// Transcribing. Keyed by local midnight; null is the undated row.
  static Map<DateTime?, String> _dayStatuses(List<_Day> days, List<_PendingItem> undated, AppLocalizations l) {
    final statuses = <DateTime?, String>{};
    final waiting = <DateTime?>[];
    void classify(DateTime? day, List<_PendingItem> items) {
      if (items.any((i) => i.moving)) {
        statuses[day] = l.onTheWayDayUploading;
      } else if (items.any((i) => i.step == 1)) {
        waiting.add(day);
      } else {
        statuses[day] = l.transcribing;
      }
    }

    // Oldest first: the order the upload drain takes them.
    for (final day in days.reversed) {
      classify(day.day, day.items);
    }
    final undatedRecordings = undated.where((i) => i.isRecording).toList();
    if (undatedRecordings.isNotEmpty) classify(null, undatedRecordings);
    for (var i = 0; i < waiting.length; i++) {
      statuses[waiting[i]] = i == 0 ? l.onTheWayDayNext : l.onTheWayDayQueued;
    }
    return statuses;
  }
}

/// What On the Way lists, split by whether a trustworthy day exists.
class _PendingWork {
  _PendingWork(this.dated, this.undated);

  /// Builds the rows from the inventory, processing conversations and server work. The page
  /// lists only work still moving: a failed or refused recording recovers without the user and is
  /// not a row.
  factory _PendingWork.collect(
    SyncProvider p,
    List<ServerConversation> processing,
    List<PendingWorkItem> serverWork,
    AppLocalizations l,
  ) {
    final processingIds = {for (final c in processing) c.id};
    final dated = <_PendingItem>[for (final c in processing) _PendingItem.processing(c, l)];
    // A live capture's uploaded audio carries the id of the conversation already listed as
    // processing, so it is not repeated.
    final inFlight = [
      for (final w in [...SyncPendingWork.uploaded(p), ...SyncPendingWork.syncing(p)])
        if (w.conversationId == null || !processingIds.contains(w.conversationId)) w,
    ];
    // The lists partition by WAL status, so a fragment never repeats across them; a phone copy
    // and its wearable source can share an id, and dropping one would hide the state the block
    // must show.
    final pending = [...inFlight]..sort((a, b) => b.timerStart.compareTo(a.timerStart));
    // Rows with no trustworthy time: server work the phone did not start, and recordings whose
    // device clock predates the plausibility floor.
    final undated = <_PendingItem>[];
    for (final block in groupRecordingBlocks(pending, joinDeviceCopies: true)) {
      final _PendingItem item;
      if (block.state == WalSyncDisplayState.uploadRejected || SyncPendingWork.needsAttention(block.state)) {
        item = _PendingItem.block(
          block,
          label: walAttentionLabel(block.state, l, rejectionReason: block.representative.uploadRejectionReason),
          step: 0,
        );
      } else if (block.wals.every((w) => w.status == WalStatus.uploaded)) {
        item = _PendingItem.block(block, label: l.transcribing, step: 2);
      } else {
        item = _PendingItem.block(block, label: _syncingLabel(block, l), step: 1);
      }
      (item.start == null ? undated : dated).add(item);
    }

    // Server work the phone did not start (another device, or a relaunch mid-job) is what the
    // device's tile stands for when nothing local is pending: list it by the same rule, so the
    // page never opens on "all synced". A conversation already listed as processing is not
    // repeated, and a sync job the phone is itself running is covered by its recordings.
    final phoneSyncing = inFlight.isNotEmpty || SyncPendingWork.hasServerJobs(p);
    for (final work in serverWork) {
      if (work.conversationIds.any(processingIds.contains)) continue;
      if (work.kind == 'sync_job' && phoneSyncing) continue;
      final item = _PendingItem.server(work, l);
      (item.start == null ? undated : dated).add(item);
    }
    // A sync can be mid-run with no recording listed yet (WAL-less processing): not "all synced".
    if ([...dated, ...undated].every((i) => i.needsAttention) && SyncPendingWork.hasServerJobs(p)) {
      final phase = p.syncState.phase;
      final transferring = p.syncState.isSyncing &&
          !p.syncState.isFetchingConversations &&
          (phase == SyncPhase.downloadingFromDevice ||
              phase == SyncPhase.waitingForInternet ||
              phase == SyncPhase.uploadingToCloud);
      undated.add(_PendingItem.status(label: SyncPendingWork.stageLabel(p, l), step: transferring ? 1 : 2));
    }
    return _PendingWork(dated, undated);
  }

  final List<_PendingItem> dated;
  final List<_PendingItem> undated;

  /// Recordings with audio behind them that have no trustworthy day.
  List<_PendingItem> get undatedRecordings => undated.where((i) => i.isRecording).toList();

  /// The stage line shown when a sync runs with no recording listed yet.
  _PendingItem? get status => undated.where((i) => !i.isRecording).firstOrNull;

  bool get isEmpty => dated.isEmpty && undated.isEmpty;

  static String _syncingLabel(RecordingBlock block, AppLocalizations l) {
    final onDevice = walIsOnDevice(block.representative);
    final moving = block.state == WalSyncDisplayState.syncing;
    if (onDevice) return moving ? l.syncCardDownloadingTitle : l.syncStatusOnDevice;
    return moving ? l.syncCardUploadingTitle : l.syncStatusWaiting;
  }
}

class _PendingItem {
  /// A conversation already on the server, writing itself now.
  _PendingItem.processing(ServerConversation conversation, AppLocalizations l)
      : start = (conversation.startedAt ?? conversation.createdAt).toLocal(),
        seconds = conversation.getDurationInSeconds(),
        label = l.processing,
        step = 3,
        moving = false,
        isRecording = true;

  /// A recording block's start, or null when no device clock value in the block
  /// is plausible: a never-set clock shows no time rather than a bogus one.
  static DateTime? _blockStart(RecordingBlock block) {
    final seconds = block.startSeconds;
    if (walTimerStartPlausible(seconds)) return DateTime.fromMillisecondsSinceEpoch(seconds * 1000);
    logImplausibleRecordingStart('on_the_way', block.representative.id, seconds);
    return null;
  }

  _PendingItem.block(RecordingBlock block, {required this.label, required this.step})
      : start = _blockStart(block),
        seconds = block.seconds,
        moving = block.state == WalSyncDisplayState.syncing,
        isRecording = true;

  /// A stage with no recording to name yet: only the label shows.
  const _PendingItem.status({required this.label, required this.step})
      : start = null,
        seconds = 0,
        moving = false,
        isRecording = false;

  /// Server-reported work's start, or null when unreported or before the
  /// plausibility floor (a device clock that was never set).
  static DateTime? _serverStart(PendingWorkItem work) {
    final startedAt = work.startedAt;
    if (startedAt == null) return null;
    if (recordingStartPlausible(startedAt)) return startedAt.toLocal();
    logImplausibleRecordingStart('on_the_way', work.id, startedAt.millisecondsSinceEpoch ~/ 1000);
    return null;
  }

  _PendingItem.server(PendingWorkItem work, AppLocalizations l)
      : start = _serverStart(work),
        seconds = work.durationSeconds ?? 0,
        label = work.state == 'transcribing' ? l.transcribing : l.processing,
        step = work.state == 'summarizing' ? 3 : 2,
        moving = false,
        isRecording = true;

  final DateTime? start;
  final int seconds;
  final String label;

  /// Audio moving between device, phone and server right now.
  final bool moving;

  /// False only for a bare stage line with no recording behind it.
  final bool isRecording;

  /// 1: still syncing, 2: transcribing, 3: writing the conversation, 0: failed or refused.
  final int step;

  bool get needsAttention => step == 0;
}

/// One local day of recordings, newest first.
class _Day {
  _Day(this.day, this.items);

  /// Local midnight.
  final DateTime day;
  final List<_PendingItem> items;
}

/// Groups dated items by the local day they started on, newest day and newest row first. A
/// recording that runs past midnight stays on the day it started.
List<_Day> _groupByDay(List<_PendingItem> items) {
  final byDay = <DateTime, List<_PendingItem>>{};
  for (final item in [...items.where((i) => i.start != null)]..sort((a, b) => b.start!.compareTo(a.start!))) {
    final s = item.start!;
    byDay.putIfAbsent(DateTime(s.year, s.month, s.day), () => []).add(item);
  }
  return [for (final e in byDay.entries) _Day(e.key, e.value)];
}

String _dayKey(DateTime day) =>
    '${day.year}-${day.month.toString().padLeft(2, '0')}-${day.day.toString().padLeft(2, '0')}';

/// "9 recordings · 1h 12m"; just the count when no length is known yet (server work).
String _totals(List<_PendingItem> items, AppLocalizations l) {
  final seconds = items.fold(0, (s, i) => s + i.seconds);
  final count = l.onTheWayRecordingCount(items.length);
  return seconds > 0 ? '$count · ${OmiDuration.compact(seconds, l)}' : count;
}

/// One day: its name, its totals underneath, and a quiet status. Sized like a settings row; at
/// large text the status moves under the totals so neither the day nor the status is cut.
class _DayRow extends StatelessWidget {
  const _DayRow({super.key, required this.title, required this.subtitle, required this.status});

  final String title;
  final String subtitle;
  final String status;

  @override
  Widget build(BuildContext context) {
    final stacked = MediaQuery.textScalerOf(context).scale(1) > 1.5;
    final statusText = Text(status, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary));
    final texts = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(title, style: OmiType.body),
        const SizedBox(height: 2),
        Text(subtitle, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
        if (stacked) ...[const SizedBox(height: 2), statusText],
      ],
    );
    return MergeSemantics(
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 48),
        child: Padding(
          padding: const EdgeInsets.all(OmiSpacing.md),
          child: stacked
              ? Align(alignment: AlignmentDirectional.centerStart, child: texts)
              : Row(children: [
                  Expanded(child: texts),
                  const SizedBox(width: OmiSpacing.xs),
                  statusText,
                ]),
        ),
      ),
    );
  }
}
