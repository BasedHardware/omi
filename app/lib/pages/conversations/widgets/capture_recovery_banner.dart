import 'package:flutter/material.dart';

import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The one banner a capture wedge owns, on Home and on the capturing page.
///
/// Tapping the banner retries the episode in place (the same recovery the monitor runs on its
/// own) — it never navigates away, because no settings page can fix a stalled BLE link from
/// where the reader stands. "What's going on?" opens the details sheet; ✕ hides the episode
/// until a newly declared trigger alerts again.
class CaptureRecoveryBanner extends StatelessWidget {
  const CaptureRecoveryBanner({super.key, this.monitor});

  final CaptureWedgeMonitor? monitor;

  @override
  Widget build(BuildContext context) {
    final wedge = monitor ?? CaptureWedgeMonitor.instance;
    return ListenableBuilder(
      listenable: wedge,
      builder: (context, _) {
        final episode = wedge.visiblePrompt;
        if (episode == null) return const SizedBox.shrink();
        final isTransferRecovery = episode.trigger == CaptureWedgeMonitor.triggerStorageAtRisk;
        if (TickerMode.valuesOf(context).enabled) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (context.mounted) wedge.markPromptShown();
          });
        }
        final l10n = context.l10n;
        final title =
            isTransferRecovery ? '${l10n.phoneStorage}: ${l10n.recordingsNotSynced}' : l10n.captureRecoveryBanner;
        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
          child: Semantics(
            button: true,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () {
                wedge.onRecoveryActioned(surface: 'banner');
                wedge.retryVisibleEpisode();
              },
              child: Container(
                key: const Key('capture_recovery_banner'),
                padding: const EdgeInsets.only(left: 14, top: 10, bottom: 10),
                decoration: BoxDecoration(
                  color: OmiColors.surface1,
                  borderRadius: const BorderRadius.all(Radius.circular(OmiRadius.md)),
                  border: Border.all(color: OmiColors.border, width: 0.5),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Icon(Icons.warning_amber_rounded, size: 16, color: OmiColors.warning),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            title,
                            style:
                                OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
                          ),
                          // The audio-safe reassurance the capturing page must keep: a stalled
                          // link risks the transcript, never the recording. The storage episode
                          // already says what is unsynced, so it needs no second line.
                          if (!isTransferRecovery) ...[
                            const SizedBox(height: 2),
                            Text(
                              l10n.captureAudioSavedTranscribesLater,
                              style: OmiType.caption.copyWith(color: OmiColors.textTertiary),
                            ),
                          ],
                        ],
                      ),
                    ),
                    TextButton(
                      key: const Key('capture_recovery_banner_info'),
                      onPressed: () => LiveCaptureCard.showDetails(
                        context,
                        title: title,
                        explanation: isTransferRecovery ? l10n.recordingsNotSynced : l10n.captureWedgeBleExplanation,
                      ),
                      style: TextButton.styleFrom(
                        foregroundColor: OmiColors.textSecondary,
                        textStyle: OmiType.footnote.copyWith(fontWeight: FontWeight.w600),
                        padding: const EdgeInsets.symmetric(horizontal: 10),
                        minimumSize: const Size(0, 36),
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        visualDensity: VisualDensity.compact,
                      ),
                      child: Text(l10n.captureBannerWhatsWrong),
                    ),
                    IconButton(
                      key: const Key('capture_recovery_banner_dismiss'),
                      tooltip: l10n.captureBannerDismiss,
                      onPressed: () => wedge.dismissDeviceEpisode(episode.deviceId),
                      icon: const Icon(Icons.close),
                      iconSize: 16,
                      color: OmiColors.textTertiary,
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
                      visualDensity: VisualDensity.compact,
                      splashRadius: 18,
                    ),
                    const SizedBox(width: 8),
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
