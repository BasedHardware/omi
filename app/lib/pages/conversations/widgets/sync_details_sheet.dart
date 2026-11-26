import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/wal_syncs.dart';
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

/// Where unsynced audio is right now. Transfer speed, file and server-job counts
/// and the firmware version are diagnostics, not progress: they are not shown,
/// only included in the text the copy button puts on the clipboard for support.
class SyncDetailsSheet extends StatefulWidget {
  const SyncDetailsSheet({super.key, required this.sync, required this.device, required this.onHowSyncingWorks});

  final SyncProvider sync;
  final DeviceProvider device;
  final VoidCallback onHowSyncingWorks;

  @override
  State<SyncDetailsSheet> createState() => _SyncDetailsSheetState();
}

class _SyncDetailsSheetState extends State<SyncDetailsSheet> {
  Timer? _freshness;

  @override
  void initState() {
    super.initState();
    _freshness = Timer.periodic(const Duration(seconds: 15), (_) => setState(() {}));
  }

  @override
  void dispose() {
    _freshness?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final sync = widget.sync;
    final device = widget.device;
    final l = context.l10n;
    final amounts = SyncPipelineAmounts.fromPending(sync.derivedWals.pendingWork);
    final state = sync.syncState;
    final jobs = sync.offlineServerProcessingCounts;
    String dur(int seconds) => OmiDuration.compact(seconds, l);

    final speed = sync.isRingDownloading
        ? sync.ringDownloadSpeedKBps
        : state.isSyncing && state.phase == SyncPhase.downloadingFromDevice
            ? state.speedKBps
            : null;
    final firmware = WalSyncs.resolveDiscoveryFirmware(
      device.currentFirmwareVersion,
      SharedPreferencesUtil().btDevice.firmwareRevision,
    );
    final isRing = WalSyncs.isRingBufferFirmware(firmware);
    final backlog = isRing
        ? (device.isConnected ? sync.freshRingBacklog : null)
        : (seconds: amounts.onDeviceSeconds, bytes: amounts.onDeviceBytes);
    final String onDevice;
    if (backlog == null) {
      onDevice = l.unknown;
    } else if (backlog.bytes > 0) {
      onDevice = '${dur(backlog.seconds)} · ${WavBytesUtil.formatBytes(backlog.bytes, decimals: 1)}';
    } else {
      onDevice = dur(backlog.seconds);
    }

    final rightNow = <(String, String)>[
      (l.syncDetailsYourOmi, device.isConnected ? l.connected : l.disconnected),
      (l.syncDetailsWaitingOnOmi, onDevice),
      (l.syncDetailsWaitingOnPhone, dur(amounts.onPhoneSeconds)),
      (l.syncDetailsTranscribing, dur(amounts.processingSeconds)),
    ];
    final forSupport = <(String, String)>[
      if (speed != null && speed > 0) (l.syncDetailsTransferSpeed, '${speed.toStringAsFixed(speed < 10 ? 1 : 0)} KB/s'),
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
          OmiButton(
            label: l.syncDetailsCopy,
            expand: true,
            onPressed: () => OmiClipboard.copy(
              context,
              [...rightNow, ...forSupport].map((e) => '${e.$1}: ${e.$2}').join('\n'),
            ),
          ),
          const SizedBox(height: OmiSpacing.sm),
          OmiButton.secondary(label: l.howSyncingWorks, expand: true, onPressed: widget.onHowSyncingWorks),
        ],
      ),
    );
  }
}
