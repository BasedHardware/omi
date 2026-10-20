import 'package:flutter/material.dart';
import 'package:omi/pages/conversation_capturing/capture_state_header.dart';
import 'package:omi/pages/conversations/capture_state_labels.dart';
import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The live page's one line about a capture wedge, directly under the header: what is wrong,
/// then the action. No card and no dismiss; the line leaves on its own when audio flows again
/// (or the reader retries).
///
/// The header carries the state (it reads "Reconnecting" during an acute episode, see
/// [CaptureRecoveryStatus.overridesHeader]); this line names the cause. Tapping the message
/// opens the details sheet. "Reconnect" (or "Retry sync" for a storage episode) retries the
/// episode in place, the same recovery the monitor runs on its own; it never navigates, because
/// no settings page can fix a stalled BLE link from where the reader stands. An
/// `ingress_recovery_failed` episode gets no action: the app owns that recovery and a Dart-side
/// retry would no-op, so the line informs and explains instead.
class CaptureRecoveryStatus extends StatelessWidget {
  const CaptureRecoveryStatus({super.key, this.monitor});

  final CaptureWedgeMonitor? monitor;

  /// Whether the header should read "Reconnecting" instead of its live state: an acute link
  /// episode means audio is not reaching the app, whatever the socket says, including while the
  /// reader's retry runs. A storage episode does not; recording continues and the header stays
  /// live.
  static bool overridesHeader(CaptureWedgeMonitor monitor) => monitor.linkStalled;

  void _retry(CaptureWedgeMonitor wedge) {
    wedge.onRecoveryActioned(surface: 'live_status');
    wedge.retryVisibleEpisode();
  }

  @override
  Widget build(BuildContext context) {
    final wedge = monitor ?? CaptureWedgeMonitor.instance;
    return ListenableBuilder(
      listenable: wedge,
      builder: (context, _) {
        final episode = wedge.visiblePrompt;
        if (episode == null) return const SizedBox.shrink();
        final isTransferRecovery = episode.trigger == CaptureWedgeMonitor.triggerStorageAtRisk;
        final isIngressFailure = episode.trigger == CaptureWedgeMonitor.triggerIngressRecoveryFailed;
        if (TickerMode.valuesOf(context).enabled) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (context.mounted) wedge.markPromptShown();
          });
        }
        final l10n = context.l10n;
        // A storage message names only what the retention risk proved: a failed free-space probe
        // is not a full disk. An ingress failure proves ingress, not durability (INV-CAP-1), so its
        // message and explanation make no audio-saved claim.
        final message = isTransferRecovery
            ? (wedge.storageAtRisk?.reason == 'disk_space_unknown'
                ? l10n.activityAttentionStorageUnknownTitle
                : l10n.capturePhoneStorageFull)
            : isIngressFailure
                ? l10n.captureIngressNeedsReconnect
                : l10n.captureRecoveryBannerTitle;
        final explanation = isTransferRecovery
            ? l10n.recordingsNotSynced
            : isIngressFailure
                ? l10n.captureIngressNeedsReconnectExplanation
                : l10n.captureWedgeBleExplanation;
        return Padding(
          key: const Key('capture_recovery_status'),
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
          // Wrap, not Row: message and action share one centred line on current phones and fold
          // to two on narrow ones or long translations.
          child: Wrap(
            alignment: WrapAlignment.center,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Semantics(
                button: true,
                child: InkWell(
                  key: const Key('capture_recovery_status_details'),
                  borderRadius: OmiRadius.smAll,
                  // Fire-and-forget: opening the sheet is navigation, not a job.
                  onTap: () => LiveCaptureCard.showDetails(context, title: message, explanation: explanation),
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(minHeight: 44),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxs),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Flexible(
                            child: Text(
                              message,
                              textAlign: TextAlign.center,
                              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                            ),
                          ),
                          if (!isIngressFailure)
                            ExcludeSemantics(
                              child: Text(' ·', style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
                            ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
              if (!isIngressFailure)
                OmiButton.tertiary(
                  key: const Key('capture_recovery_status_retry'),
                  label: isTransferRecovery ? l10n.captureBannerRetrySync : l10n.reconnect,
                  onPressed: () => _retry(wedge),
                  size: OmiButtonSize.compact,
                ),
            ],
          ),
        );
      },
    );
  }
}

/// The live page's header, listening to the wedge monitor on its own so a stall re-labels it
/// without rebuilding the transcript. While an acute link episode is open and the page would
/// otherwise read live, the header reads "Reconnecting": audio is not reaching the app, and the
/// [CaptureRecoveryStatus] line under it names why. A reader pause or a call keeps its own label.
class CaptureWedgeAppBar extends StatelessWidget implements PreferredSizeWidget {
  const CaptureWedgeAppBar({
    super.key,
    this.monitor,
    required this.showStatus,
    required this.state,
    this.bufferingFor,
    this.sourceLabel,
  });

  /// Injectable for tests; defaults to [CaptureWedgeMonitor.instance].
  final CaptureWedgeMonitor? monitor;
  final bool showStatus;
  final CaptureDisplayState state;
  final Duration? bufferingFor;
  final String? sourceLabel;

  static const _live = {CaptureDisplayState.listening, CaptureDisplayState.capturing, CaptureDisplayState.recording};

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight);

  @override
  Widget build(BuildContext context) {
    final wedge = monitor ?? CaptureWedgeMonitor.instance;
    return ListenableBuilder(
      listenable: wedge,
      builder: (context, _) {
        final stalled = _live.contains(state) && CaptureRecoveryStatus.overridesHeader(wedge);
        return ConversationStateAppBar(
          showStatus: showStatus || stalled,
          state: stalled ? CaptureDisplayState.reconnecting : state,
          bufferingFor: bufferingFor,
          sourceLabel: sourceLabel,
        );
      },
    );
  }
}
