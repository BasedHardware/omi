import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/recording_blocks.dart';
import 'package:omi/pages/conversations/sync_pending_work.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/sync/offline_sync_amounts.dart';

/// Recordings on their way to becoming conversations, opened from the device's
/// Catching up card. A summary line, then one pinned header per local day with that
/// day's totals: Today opens by default and older days fold to their totals.
/// Each row shows how close it is to done; device storage, retries and past
/// syncs stay on the Offline Sync page behind Sync Details.
class OnTheWayPage extends StatefulWidget {
  const OnTheWayPage({super.key, this.syncProvider, this.multiFileSync, this.clock, this.pendingWork});

  /// Injectable for tests and the visual audit; defaults to the app provider.
  final SyncProvider? syncProvider;

  /// Injectable Sync Details routing for tests and the visual audit.
  final bool? multiFileSync;

  /// Injectable "now" for tests and the visual audit: which day is Today.
  final DateTime Function()? clock;

  /// Server work the device's Catching up card also stands for. Injectable for tests; defaults to
  /// [PendingWorkStore.instance].
  final PendingWorkStore? pendingWork;

  /// Days opened or closed this app session, by local midnight. A day not here is open only when it
  /// is today. Memory only: after a restart the page opens on Today again.
  static final Map<DateTime, bool> _folds = {};

  @visibleForTesting
  static void resetFolds() => _folds.clear();

  @override
  State<OnTheWayPage> createState() => _OnTheWayPageState();
}

class _OnTheWayPageState extends State<OnTheWayPage> {
  late final PendingWorkStore _store = widget.pendingWork ?? PendingWorkStore.instance;

  bool _isOpen(DateTime day, DateTime today) => OnTheWayPage._folds[day] ?? day == today;

  @override
  void initState() {
    super.initState();
    _store.addListener(_onPendingWork);
  }

  @override
  void dispose() {
    _store.removeListener(_onPendingWork);
    super.dispose();
  }

  void _onPendingWork() {
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return Consumer<SyncProvider>(
      builder: (context, sync, child) {
        final p = widget.syncProvider ?? sync;
        final processing = context.watch<ConversationProvider?>()?.processingConversations ?? const [];
        final processingIds = {for (final c in processing) c.id};
        final items = <_PendingItem>[
          for (final c in processing)
            _PendingItem(
              start: (c.startedAt ?? c.createdAt).toLocal(),
              seconds: c.getDurationInSeconds(),
              label: l.processing,
              step: 3,
            ),
        ];
        // One recording's fragments can straddle stages (an upload batch done, the next still
        // syncing): group every pending fragment first, then a block is only as far along as
        // its least advanced part. A live capture's uploaded audio carries the id of the conversation
        // already listed as processing, so it is not repeated.
        final inFlight = [
          for (final w in [...SyncPendingWork.uploaded(p), ...SyncPendingWork.syncing(p)])
            if (w.conversationId == null || !processingIds.contains(w.conversationId)) w,
        ];
        final pending = [
          ...inFlight,
          // Refused fragments of the same recording join the same grouping: a block
          // selects its worst state, so a recording mid-upload with one refused
          // fragment reads once — as refused — instead of twice, as both. The three
          // lists partition by WAL status, so a fragment never repeats across them;
          // a phone copy and its wearable source can share an id, and dropping one
          // would hide the terminal state the block must show.
          ...SyncPendingWork.attention(p),
        ]..sort((a, b) => b.timerStart.compareTo(a.timerStart));
        // Rows with no trustworthy time: server work the phone did not start, and
        // recordings whose device clock predates the plausibility floor.
        final undated = <_PendingItem>[];
        for (final block in groupRecordingBlocks(pending, joinDeviceCopies: true)) {
          _PendingItem item;
          if (SyncPendingWork.needsAttention(block.state)) {
            // Refused recordings stay on the day they were made, in the Offline Sync page's words.
            item = _PendingItem.block(block, label: _attentionLabel(block.state, l), step: 0);
          } else if (block.wals.every((w) => w.status == WalStatus.uploaded)) {
            item = _PendingItem.block(block, label: l.transcribing, step: 2);
          } else {
            item = _PendingItem.block(block, label: _syncingLabel(block, l), step: 1);
          }
          // A time before the plausibility floor is a device clock that was never set:
          // the recording still counts, listed without a time rather than on a bogus day.
          (item.start == null ? undated : items).add(item);
        }

        // Server work the phone did not start (another device, or a relaunch mid-job) is what the device's
        // card stands for when nothing local is pending: list it by the same rule, so the row never
        // opens on "all synced". A conversation already listed as processing is not repeated, and a
        // sync job the phone is itself running is covered by its recordings or its status line;
        // a refused recording is not one the phone is running.
        final phoneSyncing = inFlight.isNotEmpty || SyncPendingWork.hasServerJobs(p);
        for (final work in _store.pending) {
          if (work.conversationIds.any(processingIds.contains)) continue;
          if (work.kind == 'sync_job' && phoneSyncing) continue;
          final item = _PendingItem.server(work, l);
          (item.start == null ? undated : items).add(item);
        }
        // A sync can be mid-run with no recording listed yet (WAL-less processing), and refused
        // recordings are not pending: neither is "all synced".
        if (items.every((i) => i.needsAttention) && SyncPendingWork.hasServerJobs(p)) {
          final status = SyncPendingWork.stageLabel(p, l);
          final phase = p.syncState.phase;
          final transferring = p.syncState.isSyncing &&
              !p.syncState.isFetchingConversations &&
              (phase == SyncPhase.downloadingFromDevice ||
                  phase == SyncPhase.waitingForInternet ||
                  phase == SyncPhase.uploadingToCloud);
          undated.add(_PendingItem.status(label: status, step: transferring ? 1 : 2));
        }

        final Widget body;
        if (items.isEmpty && undated.isEmpty) {
          body = OmiEmptyState(icon: Icons.check_circle_outline, title: l.allRecordingsSynced);
        } else {
          final now = (widget.clock ?? DateTime.now)();
          final today = DateTime(now.year, now.month, now.day);
          final days = _groupByDay(items);
          final dates = OmiDateFormat(
            locale: Localizations.localeOf(context),
            use24HourFormat: MediaQuery.maybeAlwaysUse24HourFormatOf(context) ?? false,
            l10n: l,
            clock: widget.clock,
          );
          void openDetails() => openOfflineSyncDetails(context, p, multiFileSync: widget.multiFileSync);
          const gutter = EdgeInsets.symmetric(horizontal: OmiSpacing.md);
          body = CustomScrollView(
            slivers: [
              if (items.isNotEmpty)
                SliverPadding(padding: gutter, sliver: SliverToBoxAdapter(child: _Summary(items: items))),
              if (undated.isNotEmpty)
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, 0),
                  sliver: SliverToBoxAdapter(child: _Group(items: undated, dates: dates)),
                ),
              for (var i = 0; i < days.length; i++)
                SliverPadding(
                  padding: gutter,
                  sliver: SliverMainAxisGroup(
                    slivers: [
                      // Sizes to its content, so the header grows with the text size instead of
                      // clipping.
                      PinnedHeaderSliver(
                        child: Padding(
                          padding: EdgeInsets.only(top: i == 0 ? 4 : 0),
                          child: _DayHeader(
                            key: Key('on_the_way_day_${_dayKey(days[i].day)}'),
                            title: dates.dayHeader(days[i].day),
                            items: days[i].items,
                            expanded: _isOpen(days[i].day, today),
                            onTap: () =>
                                setState(() => OnTheWayPage._folds[days[i].day] = !_isOpen(days[i].day, today)),
                          ),
                        ),
                      ),
                      if (_isOpen(days[i].day, today))
                        SliverToBoxAdapter(
                          child: Padding(
                            padding: const EdgeInsets.only(bottom: OmiSpacing.xs),
                            child: _Group(items: days[i].items, dates: dates, onAttentionTap: openDetails),
                          ),
                        ),
                    ],
                  ),
                ),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.lg, OmiSpacing.md, OmiSpacing.xxl),
                sliver: SliverToBoxAdapter(
                  child: Material(
                    key: const Key('on_the_way_sync_details'),
                    color: OmiColors.surface1,
                    borderRadius: OmiRadius.xlAll,
                    child: InkWell(
                      borderRadius: OmiRadius.xlAll,
                      onTap: openDetails,
                      child: Padding(
                        padding: const EdgeInsetsDirectional.fromSTEB(OmiSpacing.md, 14, 10, 14),
                        child: Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(l.syncDetailsTitle, style: OmiType.body),
                                  if (items.any((i) => i.needsAttention)) ...[
                                    const SizedBox(height: 3),
                                    Text(
                                      l.syncCardNeedsAttention(items.where((i) => i.needsAttention).length),
                                      style: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
                                    ),
                                  ],
                                ],
                              ),
                            ),
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
        }
        return Scaffold(
          appBar: AppBar(leading: const OmiBackButton(), title: Text(l.onTheWayTitle)),
          body: body,
        );
      },
    );
  }

  static String _dayKey(DateTime day) =>
      '${day.year}-${day.month.toString().padLeft(2, '0')}-${day.day.toString().padLeft(2, '0')}';

  /// The Offline Sync page's own reason for each refused state.
  static String _attentionLabel(WalSyncDisplayState state, AppLocalizations l) => switch (state) {
        WalSyncDisplayState.corrupted => l.syncStatusFileUnavailable,
        WalSyncDisplayState.outsideRecoveryWindow => l.syncStatusTooOld,
        WalSyncDisplayState.unsupportedAudio => l.syncStatusUnsupportedAudio,
        WalSyncDisplayState.uploadRejected => l.failedStatus,
        _ => l.syncStatusFailed,
      };

  static String _syncingLabel(RecordingBlock block, AppLocalizations l) {
    final onDevice = walIsOnDevice(block.representative);
    final moving = block.state == WalSyncDisplayState.syncing;
    if (onDevice) return moving ? l.syncCardDownloadingTitle : l.syncStatusOnDevice;
    return moving ? l.syncCardUploadingTitle : l.syncStatusWaiting;
  }
}

class _PendingItem {
  const _PendingItem({required this.start, required this.seconds, required this.label, required this.step});

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
        seconds = block.seconds;

  /// A stage with no recording to name yet: only the label shows.
  const _PendingItem.status({required this.label, required this.step})
      : start = null,
        seconds = 0;

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
        step = work.state == 'summarizing' ? 3 : 2;

  final DateTime? start;
  final int seconds;
  final String label;

  /// 1: still syncing, 2: transcribing, 3: writing the conversation, 0: refused, needs attention.
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

/// "9 recordings · 1h 12m".
String _totals(List<_PendingItem> items, AppLocalizations l) =>
    '${l.onTheWayRecordingCount(items.length)} · ${OmiDuration.compact(items.fold(0, (s, i) => s + i.seconds), l)}';

/// Only the states worth a glance ("2 uploading · 1 needs attention"), never "36 transcribing".
(String?, String?) _exceptions(List<_PendingItem> items, AppLocalizations l) {
  final uploading = items.where((i) => i.step == 1).length;
  final almostReady = items.where((i) => i.step == 3).length;
  final attention = items.where((i) => i.needsAttention).length;
  final moving = [
    if (uploading > 0) l.onTheWayUploadingCount(uploading),
    if (almostReady > 0) l.onTheWayAlmostReadyCount(almostReady),
  ];
  return (moving.isEmpty ? null : moving.join(' · '), attention > 0 ? l.onTheWayNeedsAttentionCount(attention) : null);
}

/// "45 recordings · 8h 54m on the way" over its exceptions.
class _Summary extends StatelessWidget {
  const _Summary({required this.items});

  final List<_PendingItem> items;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final (moving, attention) = _exceptions(items, l);
    final extra = [if (moving != null) moving, if (attention != null) attention];
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.xxs, OmiSpacing.xs, OmiSpacing.xxs, OmiSpacing.xxs),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(l.onTheWaySummary(_totals(items, l)), style: OmiType.headline),
          if (extra.isNotEmpty) ...[
            const SizedBox(height: 3),
            Text(extra.join(' · '), style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
          ],
        ],
      ),
    );
  }
}

/// A day's pinned header: its name, totals and exceptions, with needs attention in warning colour.
/// Tapping it opens or folds the day.
class _DayHeader extends StatelessWidget {
  const _DayHeader({super.key, required this.title, required this.items, required this.expanded, required this.onTap});

  final String title;
  final List<_PendingItem> items;
  final bool expanded;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final (moving, attention) = _exceptions(items, l);
    return Semantics(
      header: true,
      expanded: expanded,
      child: InkWell(
        onTap: onTap,
        child: Container(
          color: OmiColors.surface0,
          constraints: const BoxConstraints(minHeight: 44),
          padding: const EdgeInsetsDirectional.fromSTEB(OmiSpacing.xxs, 12, 0, 8),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: OmiType.body.copyWith(fontWeight: FontWeight.w600)),
                    const SizedBox(height: 2),
                    Text.rich(
                      TextSpan(
                        children: [
                          TextSpan(text: _totals(items, l)),
                          if (moving != null) TextSpan(text: ' · $moving'),
                          if (attention != null)
                            TextSpan(text: ' · $attention', style: TextStyle(color: OmiColors.warning)),
                        ],
                      ),
                      style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                    ),
                  ],
                ),
              ),
              Icon(expanded ? Icons.expand_less : Icons.expand_more, color: OmiColors.textTertiary),
            ],
          ),
        ),
      ),
    );
  }
}

class _Group extends StatelessWidget {
  const _Group({required this.items, required this.dates, this.onAttentionTap});

  final List<_PendingItem> items;
  final OmiDateFormat dates;

  /// A refused row is not progressing: it opens Sync Details instead of showing the bars.
  final VoidCallback? onAttentionTap;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return Material(
      color: OmiColors.surface1,
      borderRadius: OmiRadius.xlAll,
      clipBehavior: Clip.antiAlias,
      child: Column(
        children: [
          for (var i = 0; i < items.length; i++) ...[
            if (i > 0) Divider(height: 1, thickness: 1, indent: OmiSpacing.md, color: OmiColors.surface2),
            Semantics(
              liveRegion: true,
              button: items[i].needsAttention,
              label: [
                if (items[i].start != null) dates.time(items[i].start!),
                if (items[i].seconds > 0) OmiDuration.compact(items[i].seconds, l),
                items[i].label,
              ].join(', '),
              excludeSemantics: true,
              child: InkWell(
                onTap: items[i].needsAttention ? onAttentionTap : null,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 14),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            if (items[i].start != null) ...[
                              Text(
                                items[i].seconds > 0
                                    ? '${dates.time(items[i].start!)} · ${OmiDuration.compact(items[i].seconds, l)}'
                                    : dates.time(items[i].start!),
                                style: OmiType.body,
                              ),
                              const SizedBox(height: 3),
                              Text(
                                items[i].label,
                                style: OmiType.subhead.copyWith(
                                  color: items[i].needsAttention ? OmiColors.warning : OmiColors.textTertiary,
                                ),
                              ),
                            ] else
                              Text(items[i].label, style: OmiType.body),
                          ],
                        ),
                      ),
                      if (items[i].needsAttention)
                        Icon(Icons.chevron_right, color: OmiColors.textTertiary)
                      else
                        _Steps(step: items[i].step),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Three short bars: synced, transcribed, written.
class _Steps extends StatelessWidget {
  const _Steps({required this.step});

  final int step;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 1; i <= 3; i++)
          Container(
            margin: const EdgeInsetsDirectional.only(start: 4),
            width: 14,
            height: 4,
            decoration: BoxDecoration(
              color: i <= step ? OmiColors.accent : OmiColors.surface3,
              borderRadius: OmiRadius.pillAll,
            ),
          ),
      ],
    );
  }
}
