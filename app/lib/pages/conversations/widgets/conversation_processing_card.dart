import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/pages/conversations/recording_blocks.dart';
import 'package:omi/pages/conversations/sync_cooldown_copy.dart';
import 'package:omi/pages/conversations/sync_page.dart';
import 'package:omi/pages/conversations/widgets/sync_step_bar.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/sync/offline_sync_amounts.dart';

/// Home's Offline Sync status card: what happened to the recordings the pendant
/// or phone just saved, at a glance, with a tap-through to the Offline Sync
/// page the device settings open ([AutoSyncPage] for multi-file devices,
/// [SyncPage] otherwise).
///
/// Home used to go quiet the moment a conversation ended: the recording sat in
/// the pipeline — device → phone → server — and the newest visible row kept its
/// old timestamp, which read as "stuck". This card keeps that work on screen,
/// in the same audio-length numbers and the same three-step bar the Offline
/// Sync pages use, and disappears once every recording is a conversation.
///
/// The copy is the Offline Sync status card's, reused key for key, so Home and
/// the settings page can never disagree about what a sync is doing.
class ConversationProcessingCard extends StatefulWidget {
  const ConversationProcessingCard({super.key, this.syncProvider, this.multiFileSync});

  /// Injectable for tests and the visual audit; defaults to the app provider.
  final SyncProvider? syncProvider;

  /// Injectable page routing for tests and the visual audit; null reads the
  /// paired device's multi-file-sync capability from preferences.
  final bool? multiFileSync;

  @override
  State<ConversationProcessingCard> createState() => _ConversationProcessingCardState();
}

class _ConversationProcessingCardState extends State<ConversationProcessingCard> {
  // In State, not on the widget, so an ancestor rebuild (connectivity flips,
  // home-shell provider notifications) cannot reset the run snapshot mid-sync —
  // the amounts would shrink under the bar instead of the bar filling.
  // AutoSyncPage holds its tracker the same way.
  final SyncRunTracker _runTracker = SyncRunTracker();

  static bool _needsAttention(WalSyncDisplayState s) =>
      s == WalSyncDisplayState.failed ||
      s == WalSyncDisplayState.corrupted ||
      s == WalSyncDisplayState.outsideRecoveryWindow ||
      s == WalSyncDisplayState.unsupportedAudio ||
      s == WalSyncDisplayState.uploadRejected;

  /// Whether a recording still has forward-moving work ahead of it: waiting
  /// for a sync, retrying one, or in one now. Terminal recordings (retries
  /// exhausted, refused by the server) are handled on the Offline Sync page;
  /// they must not hold a card on Home forever.
  static bool _isForwardMoving(WalSyncDisplayState s) =>
      s == WalSyncDisplayState.waiting || s == WalSyncDisplayState.retrying || s == WalSyncDisplayState.syncing;

  /// Visible while recordings are still on their way to becoming
  /// conversations: anything uploading or transcribing, any sync or fetch in
  /// flight, and anything waiting to be drained — auto-sync will take it, the
  /// tap starts it, and either way that beats a stale timestamp. Recordings
  /// the server refused (too old, unreadable, retries exhausted) are surfaced
  /// by the attention copy below while anything actionable is still up, then
  /// handled on the Offline Sync page; they do not keep a card up on their
  /// own forever.
  bool _shouldShow(SyncProvider p) {
    if (p.uploadedWals.isNotEmpty || p.syncState.isProcessing) return true;
    return p.allWals.any((w) => w.status == WalStatus.miss && _isForwardMoving(w.syncDisplayState));
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<SyncProvider>(
      builder: (context, sync, child) {
        final p = widget.syncProvider ?? sync;
        if (!_shouldShow(p)) return const SizedBox.shrink();
        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
          child: Semantics(
            button: true,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () {
                // The device settings' gate, key for key: without device-storage
                // support there is no Offline Sync screen to open, only the
                // explanation of why (device_settings' _openOfflineSync).
                if (!context.read<DeviceProvider>().isDeviceStorageSupport) {
                  showOmiAlert(context, title: context.l10n.v2Undetected, message: context.l10n.v2UndetectedMessage);
                  return;
                }
                final multi = widget.multiFileSync ?? SharedPreferencesUtil().deviceSupportsMultiFileSync;
                routeToPage(context, multi ? const AutoSyncPage() : const SyncPage());
              },
              child: Container(
                key: const Key('conversation_processing_card'),
                width: double.maxFinite,
                constraints: const BoxConstraints(minHeight: 44),
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                decoration: BoxDecoration(
                  color: OmiColors.surface1,
                  borderRadius: const BorderRadius.all(Radius.circular(OmiRadius.md)),
                ),
                child: _buildContent(context, p),
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildContent(BuildContext context, SyncProvider p) {
    final l = context.l10n;
    final s = p.syncState;
    String dur(int seconds) => OmiDuration.compact(seconds, l);

    final step = _runTracker.update(s, p.allWals);
    // The settings page's active window: a sync in flight, or the
    // conversation fetch that follows it. Reading only isSyncing here let
    // Home drop to ready copy during the fetch while the settings page
    // still said processing.
    final bool isActive = s.isProcessing;
    final bool spinner = (isActive || p.uploadedWals.isNotEmpty) && !p.isRateLimited;

    String title;
    String? subtitle;
    Color titleColor = OmiColors.textPrimary;
    SyncStep? barStep;
    double? barFraction;

    if (isActive && step != null && step.step != SyncStep.transcribe) {
      // A sync is moving audio right now; mirror the settings page's card.
      final run = _runTracker.runSeconds ?? 0;
      title = run > 0 ? l.syncCardSyncingAmount(dur(run)) : l.syncCardSyncingTitle;
      barStep = step.barStep;
      final known = step.totalSeconds > 0;
      if (step.step == SyncStep.download) {
        subtitle = known ? l.syncStepDownloadingAmount(dur(step.doneSeconds), dur(step.totalSeconds)) : null;
        // The device reports a byte fraction before any audio is countable.
        barFraction = s.progress > 0 ? s.progress : null;
      } else if (s.phase == SyncPhase.waitingForInternet) {
        title = l.syncCardWaitingInternet;
        titleColor = Colors.orangeAccent;
        barFraction = known ? step.fraction : 0;
      } else {
        subtitle = known ? l.syncStepUploadingAmount(dur(step.doneSeconds), dur(step.totalSeconds)) : null;
        barFraction = known && step.doneSeconds > 0 ? step.fraction : null;
      }
      // Live-capture uploads run before the device drain: the bar stays on the device step.
      if (barStep != step.step) barFraction = 0;
    } else if (p.isRateLimited) {
      title = syncCooldownTitle(p.rateLimitReason, l);
      titleColor = Colors.orangeAccent;
    } else if (isActive || p.uploadedWals.isNotEmpty) {
      // Uploads finished; the server is turning them into conversations.
      final job = p.offlineServerProcessingSeconds;
      title = job.totalSeconds > 0 ? l.syncCardTranscribingAmount(dur(job.totalSeconds)) : l.syncCardProcessing;
      subtitle = job.tracked && job.totalSeconds > 0
          ? l.syncCardTranscribedOf(dur(job.doneSeconds), dur(job.totalSeconds))
          : l.syncProcessingBackgroundHint;
      barStep = SyncStep.transcribe;
      barFraction = job.tracked && job.doneSeconds > 0 ? job.doneSeconds / job.totalSeconds : null;
    } else {
      // Nothing in flight. Recordings the server refused read before the ones
      // merely waiting, as on the Offline Sync page; the page owns the detail.
      final attentionWals = p.allWals.where((w) => _needsAttention(w.syncDisplayState)).toList();
      if (attentionWals.isNotEmpty) {
        title = l.syncCardNeedsAttention(groupRecordingBlocks(attentionWals).length);
        titleColor = Colors.orangeAccent;
      } else {
        final readyWals = p.allWals.where((w) => w.status == WalStatus.miss && walIsSyncable(w)).toList();
        final seconds = walSeconds(readyWals);
        title = seconds > 0
            ? l.syncCardReadyAmount(dur(seconds))
            : l.syncCardReadyCount(groupRecordingBlocks(readyWals).length);
      }
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            if (spinner) ...[const OmiSpinner(size: OmiSpinnerSize.small), const SizedBox(width: 10)],
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    title,
                    style: TextStyle(color: titleColor, fontSize: 15, fontWeight: FontWeight.w500, height: 1.25),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (subtitle != null) ...[
                    const SizedBox(height: 3),
                    Text(
                      subtitle,
                      style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: 10),
            FaIcon(FontAwesomeIcons.chevronRight, color: OmiColors.textTertiary, size: 12),
          ],
        ),
        if (barStep != null) ...[
          const SizedBox(height: 12),
          SyncStepBar(step: barStep, fraction: barFraction),
        ],
      ],
    );
  }
}
