import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The one banner a capture wedge owns, on Home and on the capturing page: a warning card,
/// not a toast.
///
/// Tapping the card retries the episode in place (the same recovery the monitor runs on its
/// own) — it never navigates away, because no settings page can fix a stalled BLE link from
/// where the reader stands. "Try reconnect" runs that same retry; "What's going on?" opens the
/// details sheet; ✕ hides the episode until a newly declared trigger alerts again. An
/// `ingress_recovery_failed` episode is the exception: the app itself owns that recovery and a
/// Dart-side retry would no-op, so the card informs and explains instead of offering a retry.
class CaptureRecoveryBanner extends StatelessWidget {
  const CaptureRecoveryBanner({super.key, this.monitor});

  final CaptureWedgeMonitor? monitor;

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
        if (episode == null) return const SizedBox.shrink();
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
        final title = isTransferRecovery
            ? '${l10n.phoneStorage}: ${l10n.recordingsNotSynced}'
            : isIngressFailure
                ? l10n.captureIngressNeedsReconnect
                : l10n.captureRecoveryBanner;
        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
          child: Semantics(
            button: !isIngressFailure,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: isIngressFailure ? null : () => _retry(wedge),
              child: Container(
                key: const Key('capture_recovery_banner'),
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  // Amber over the card surface keeps the tint a warning card in both
                  // appearances without a new palette entry.
                  color: Color.alphaBlend(OmiColors.warning.withValues(alpha: 0.12), OmiColors.surface1),
                  borderRadius: const BorderRadius.all(Radius.circular(OmiRadius.md)),
                  border: Border.all(color: OmiColors.warning.withValues(alpha: 0.35)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Row(
                      children: [
                        // The firmware update card's warning triangle: same glyph, size, and
                        // silence for screen readers, so both cards read as one family.
                        ExcludeSemantics(
                          child: FaIcon(FontAwesomeIcons.triangleExclamation, size: 18, color: OmiColors.warning),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            title,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            // textPrimary, not warning: amber-on-cream fails contrast in light
                            // mode; the icon, border, and fill already carry the warning read.
                            style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600, height: 1.35),
                          ),
                        ),
                      ],
                    ),
                    // The second line may only promise what the trigger proves: a storage
                    // episode already says what is unsynced, and an ingress failure proves
                    // ingress, not durability (INV-CAP-1) — neither gets an audio-saved claim.
                    if (!isTransferRecovery && !isIngressFailure) ...[
                      const SizedBox(height: 4),
                      Text(
                        l10n.captureLinkStalledTranscribesLater,
                        style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, height: 1.35),
                      ),
                    ],
                    const SizedBox(height: OmiSpacing.xs),
                    // Wrap, not Row: two compact buttons plus ✕ fit one line on current
                    // phones and fold to a second on narrow ones instead of overflowing.
                    Wrap(
                      spacing: OmiSpacing.xs,
                      runSpacing: 8,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        // No retry action for an exhausted native ingress recovery: the
                        // app-owned recovery is already running and a Dart retry no-ops.
                        if (!isIngressFailure)
                          OmiButton(
                            key: const Key('capture_recovery_banner_retry'),
                            label: isTransferRecovery ? l10n.captureBannerRetrySync : l10n.captureBannerTryReconnect,
                            onPressed: () => _retry(wedge),
                            size: OmiButtonSize.compact,
                            // Amber has no on-warning token; near-black clears 8:1 on both
                            // palettes' amber, white does not in light mode.
                            colors: OmiButtonColors(
                              background: OmiColors.warning,
                              foreground: Colors.black87,
                            ),
                          ),
                        OmiButton.tertiary(
                          key: const Key('capture_recovery_banner_info'),
                          label: l10n.captureBannerWhatsWrong,
                          // Fire-and-forget: opening the sheet is navigation, not a job, so the
                          // button must not spin behind it waiting for the sheet to close.
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
                        // Same filled-circle family as the capturing page's pause control.
                        OmiIconButton.filled(
                          key: const Key('capture_recovery_banner_dismiss'),
                          icon: const Icon(Icons.close, size: 16),
                          label: l10n.captureBannerDismiss,
                          onPressed: () => wedge.dismissVisibleEpisode(episode.deviceId),
                          fillColor: OmiColors.surface2,
                          diameter: 36,
                        ),
                      ],
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
