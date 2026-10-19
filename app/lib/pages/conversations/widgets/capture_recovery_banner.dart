import 'package:flutter/material.dart';
import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The one banner a capture wedge owns, on Home and on the capturing page: a warning card,
/// not a toast.
///
/// Tapping the card retries the episode in place (the same recovery the monitor runs on its
/// own) — it never navigates away, because no settings page can fix a stalled BLE link from
/// where the reader stands. "Reconnect" runs that same retry; "What's going on?" opens the
/// details sheet; ✕ hides the episode until a newly declared trigger alerts again. An
/// `ingress_recovery_failed` episode is the exception: the app itself owns that recovery and a
/// Dart-side retry would no-op, so the card informs and explains instead of offering a retry.
class CaptureRecoveryBanner extends StatelessWidget {
  const CaptureRecoveryBanner({super.key, this.monitor, this.acuteOnly = false});

  final CaptureWedgeMonitor? monitor;

  /// Home mounts the banner with this set: slow-burn episodes (storage at risk,
  /// upload silence) live in Activity's Needs attention rows, not here. The
  /// capturing page keeps the unfiltered banner — it is the one surface that
  /// must speak while the reader is watching a capture. Acute link failures
  /// (zero-byte streaks, rapid reconnects, connected-but-silent, exhausted
  /// ingress recovery) stay on Home because they ask for attention now and the
  /// live pill does not observe the monitor.
  final bool acuteOnly;

  void _retry(CaptureWedgeMonitor wedge) {
    wedge.onRecoveryActioned(surface: 'banner');
    wedge.retryVisibleEpisode();
  }

  @override
  Widget build(BuildContext context) {
    final wedge = monitor ?? CaptureWedgeMonitor.instance;
    return ListenableBuilder(
      listenable: wedge,
      builder: (context, _) {
        final episode = wedge.visiblePrompt;
        // Home asks for acute episodes only: a storage-at-risk (or upload-silence)
        // episode is slow-burn and lives in Activity's Needs attention rows
        // instead. Upload silence never reaches this slot (telemetry-only), so
        // the filter is the storage trigger.
        if (episode == null || (acuteOnly && episode.trigger == CaptureWedgeMonitor.triggerStorageAtRisk)) {
          return const SizedBox.shrink();
        }
        final isTransferRecovery = episode.trigger == CaptureWedgeMonitor.triggerStorageAtRisk;
        // Native ingress recovery is exhausted; the app keeps retrying on its own and a
        // Dart-side retry would no-op (retryVisibleEpisode returns for this trigger).
        final isIngressFailure = episode.trigger == CaptureWedgeMonitor.triggerIngressRecoveryFailed;
        if (TickerMode.valuesOf(context).enabled) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (context.mounted) wedge.markPromptShown();
          });
        }
        final l10n = context.l10n;
        final storage = wedge.storageAtRisk;
        // A storage title names only what the retention risk proved: a failed free-space probe
        // is not a full disk.
        final title = isTransferRecovery
            ? (storage?.reason == 'disk_space_unknown'
                ? l10n.activityAttentionStorageUnknownTitle
                : l10n.capturePhoneStorageFull)
            : isIngressFailure
                ? l10n.captureIngressNeedsReconnect
                : l10n.captureRecoveryBannerTitle;
        // The second line may only promise what the trigger proves: a storage episode says what
        // is unsynced, and an ingress failure proves ingress, not durability (INV-CAP-1) — it
        // gets no audio-saved claim.
        final detail = isTransferRecovery
            ? l10n.recordingsNotSynced
            : isIngressFailure
                ? null
                : l10n.captureLinkStalledTranscribesLater;
        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
          child: Semantics(
            button: !isIngressFailure,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: isIngressFailure ? null : () => _retry(wedge),
              child: Container(
                key: const Key('capture_recovery_banner'),
                decoration: BoxDecoration(
                  // Amber over the card surface keeps the tint a warning card in both
                  // appearances without a new palette entry; no border, the wash is the edge.
                  color: Color.alphaBlend(OmiColors.warning.withValues(alpha: 0.12), OmiColors.surface1),
                  borderRadius: OmiRadius.lgAll,
                ),
                child: Stack(
                  children: [
                    Padding(
                      padding: const EdgeInsetsDirectional.fromSTEB(
                          OmiSpacing.md, OmiSpacing.md, OmiSpacing.md, OmiSpacing.xs),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          ExcludeSemantics(child: Icon(Icons.warning_rounded, size: 20, color: OmiColors.warning)),
                          const SizedBox(width: OmiSpacing.sm),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                // Only the title clears the corner ✕; the detail and actions use
                                // the card's full width.
                                Padding(
                                  padding: const EdgeInsetsDirectional.only(end: 28),
                                  child: Text(
                                    title,
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                    // textPrimary, not warning: amber-on-cream fails contrast in
                                    // light mode; the icon and wash already carry the warning read.
                                    style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600, height: 1.35),
                                  ),
                                ),
                                if (detail != null) ...[
                                  const SizedBox(height: 2),
                                  Text(
                                    detail,
                                    style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, height: 1.35),
                                  ),
                                ],
                                const SizedBox(height: OmiSpacing.sm),
                                // Wrap, not Row: both actions fit one line on current phones and
                                // fold to a second on narrow ones or long translations.
                                Wrap(
                                  spacing: OmiSpacing.xxs,
                                  runSpacing: OmiSpacing.xxs,
                                  crossAxisAlignment: WrapCrossAlignment.center,
                                  children: [
                                    // No retry action for an exhausted native ingress recovery: the
                                    // app-owned recovery is already running and a Dart retry no-ops.
                                    if (!isIngressFailure)
                                      OmiButton(
                                        key: const Key('capture_recovery_banner_retry'),
                                        label: isTransferRecovery ? l10n.captureBannerRetrySync : l10n.reconnect,
                                        onPressed: () => _retry(wedge),
                                        size: OmiButtonSize.compact,
                                      ),
                                    OmiButton.tertiary(
                                      key: const Key('capture_recovery_banner_info'),
                                      label: l10n.captureBannerWhatsWrong,
                                      // Fire-and-forget: opening the sheet is navigation, not a job, so
                                      // the button must not spin behind it waiting for the sheet.
                                      onPressed: () {
                                        LiveCaptureCard.showDetails(
                                          context,
                                          title: title,
                                          explanation: isTransferRecovery
                                              ? l10n.recordingsNotSynced
                                              : isIngressFailure
                                                  ? l10n.captureIngressNeedsReconnectExplanation
                                                  : l10n.captureWedgeBleExplanation,
                                        );
                                      },
                                      size: OmiButtonSize.compact,
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                    // Dismiss sits in the corner, where every card's close lives, instead of
                    // taking a row of its own under the actions. Its 44pt target is centred on
                    // the title's first line.
                    PositionedDirectional(
                      top: OmiSpacing.xxs,
                      end: OmiSpacing.xxs,
                      child: OmiIconButton(
                        key: const Key('capture_recovery_banner_dismiss'),
                        icon: const Icon(Icons.close, size: 18),
                        label: l10n.captureBannerDismiss,
                        color: OmiColors.textTertiary,
                        onPressed: () => wedge.dismissVisibleEpisode(episode.deviceId),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}
