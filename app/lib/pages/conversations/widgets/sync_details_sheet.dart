import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/models/sync_state.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/audio/wav_bytes.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/sync/offline_sync_amounts.dart';

/// Opens [SyncDetailsSheet]. [onHowSyncingWorks] opens the explainer that used
/// to sit behind the app bar's info button.
Future<void> showSyncDetailsSheet(BuildContext context, {required VoidCallback onHowSyncingWorks}) {
  final sync = context.read<SyncProvider>();
  final device = context.read<DeviceProvider>();
  return showOmiSheet<void>(
    context: context,
    title: context.l10n.syncDetailsTitle,
    padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, OmiSpacing.xxs, OmiSpacing.xl, OmiSpacing.xl),
    // The page's providers, not a lookup from the sheet's own route.
    builder: (sheetContext) => ListenableBuilder(
      listenable: Listenable.merge([sync, device]),
      builder: (_, __) => SyncDetailsSheet(sync: sync, device: device, onHowSyncingWorks: onHowSyncingWorks),
    ),
  );
}

/// Where unsynced audio is right now, plus the raw counts support asks for.
///
/// File, upload-part and server-job counts are real diagnostics but meaningless
/// as progress, so this is the only place they appear, under their own names.
class SyncDetailsSheet extends StatelessWidget {
  const SyncDetailsSheet({super.key, required this.sync, required this.device, required this.onHowSyncingWorks});

  final SyncProvider sync;
  final DeviceProvider device;
  final VoidCallback onHowSyncingWorks;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final amounts = SyncPipelineAmounts.of(sync.allWals);
    final state = sync.syncState;
    final jobs = sync.offlineServerProcessingCounts;
    String dur(int seconds) => OmiDuration.compact(seconds, l);

    final speed = state.isSyncing && state.phase == SyncPhase.downloadingFromDevice ? state.speedKBps : null;
    final onDevice = amounts.onDeviceBytes > 0
        ? '${dur(amounts.onDeviceSeconds)} · ${WavBytesUtil.formatBytes(amounts.onDeviceBytes, decimals: 1)}'
        : dur(amounts.onDeviceSeconds);

    final rightNow = <(String, String)>[
      (l.syncDetailsYourOmi, device.isConnected ? l.connected : l.disconnected),
      if (speed != null && speed > 0) (l.syncDetailsTransferSpeed, '${speed.toStringAsFixed(speed < 10 ? 1 : 0)} KB/s'),
      (l.syncDetailsWaitingOnOmi, onDevice),
      (l.syncDetailsWaitingOnPhone, dur(amounts.onPhoneSeconds)),
      (l.syncDetailsTranscribing, dur(amounts.processingSeconds)),
    ];
    final forSupport = <(String, String)>[
      (l.syncDetailsAudioFiles, '${sync.allWals.length}'),
      if (jobs.total > 0) (l.syncDetailsServerJobs, '${jobs.processed} / ${jobs.total}'),
      (l.firmware, device.currentFirmwareVersion),
    ];

    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          OmiSettingsGroup(
            header: l.syncDetailsRightNow,
            children: [for (final (k, v) in rightNow) OmiSettingsRow(title: k, value: v, showChevron: false)],
          ),
          const SizedBox(height: OmiSpacing.xl),
          OmiSettingsGroup(
            header: l.syncDetailsForSupport,
            children: [for (final (k, v) in forSupport) OmiSettingsRow(title: k, value: v, showChevron: false)],
          ),
          const SizedBox(height: OmiSpacing.xl),
          OmiButton(
            label: l.syncDetailsCopy,
            expand: true,
            onPressed: () => OmiClipboard.copy(
              context,
              [...rightNow, ...forSupport].map((e) => '${e.$1}: ${e.$2}').join('\n'),
            ),
          ),
          const SizedBox(height: OmiSpacing.sm),
          OmiButton.secondary(label: l.howSyncingWorks, expand: true, onPressed: onHowSyncingWorks),
        ],
      ),
    );
  }
}
