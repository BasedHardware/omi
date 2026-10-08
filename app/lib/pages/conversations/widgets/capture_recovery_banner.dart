import 'dart:async';

import 'package:flutter/material.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// What the recovery prompt for [episode] says, on the banner and in the native live page.
String captureRecoveryText(AppLocalizations l10n, CaptureWedgeEpisode episode) =>
    episode.trigger == CaptureWedgeMonitor.triggerStorageAtRisk
        ? '${l10n.phoneStorage}: ${l10n.recordingsNotSynced}'
        : l10n.captureRecoveryBanner;

/// Acts on the recovery prompt for [episode]: a storage-at-risk episode retries the transfer, any
/// other opens the device settings.
Future<void> actOnCaptureRecovery(CaptureWedgeMonitor wedge, CaptureWedgeEpisode episode) async {
  final isTransferRecovery = episode.trigger == CaptureWedgeMonitor.triggerStorageAtRisk;
  wedge.onRecoveryActioned(surface: 'banner');
  if (isTransferRecovery) {
    wedge.retryVisibleEpisode();
  } else {
    await HomeNavigation.openRoute('/settings/device');
  }
}

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
        if (TickerMode.valuesOf(context).enabled) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (context.mounted) wedge.markPromptShown();
          });
        }
        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
          child: Semantics(
            button: true,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => unawaited(actOnCaptureRecovery(wedge, episode)),
              child: Container(
                key: const Key('capture_recovery_banner'),
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  color: OmiColors.surface1,
                  borderRadius: const BorderRadius.all(Radius.circular(OmiRadius.md)),
                  border: Border.all(color: OmiColors.border, width: 0.5),
                ),
                child: Row(
                  children: [
                    Icon(Icons.warning_amber_rounded, size: 16, color: OmiColors.warning),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        captureRecoveryText(context.l10n, episode),
                        style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
                      ),
                    ),
                    Icon(Icons.chevron_right, size: 16, color: OmiColors.textTertiary),
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
