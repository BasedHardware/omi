import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/providers/sync_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/header_circle_button.dart';

/// The header's Cloud button. It shows while a device is paired or while any recording is still
/// waiting (on the device, or on the phone for transcription), and carries the waiting count as a
/// badge — the one place the backlog is surfaced, so it replaces the old "Transcriptions pending"
/// row on Home. Neutral while syncing (INV-UI-1); warning tint while files wait on the device.
class HeaderSyncButton extends StatelessWidget {
  const HeaderSyncButton({super.key, required this.hasPairedDevice, required this.onTap});

  final bool hasPairedDevice;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final syncProvider = context.watch<SyncProvider>();
    final onDevice = syncProvider.missingWalsOnDevice.length;
    final onPhone = syncProvider.pendingLocalTranscriptionWals.length;
    final pending = onDevice + onPhone;
    if (!hasPairedDevice && pending == 0) return const SizedBox.shrink();

    final isSyncing = syncProvider.isSyncing;
    final hasPendingOnDevice = onDevice > 0;
    final l10n = context.l10n;
    return HeaderCircleButton(
      key: const ValueKey('header_sync_button'),
      semanticLabel: pending > 0 ? '${l10n.sync}, ${l10n.transcriptionsPendingCount(pending)}' : l10n.sync,
      onTap: onTap,
      badgeCount: pending,
      badgeColor: hasPendingOnDevice ? OmiColors.warning : null,
      color: isSyncing
          ? OmiColors.surface3
          : hasPendingOnDevice
              ? OmiColors.warning.withValues(alpha: 0.15)
              : OmiColors.surface1,
      icon: Icon(
        Icons.cloud_rounded,
        size: 18,
        color: isSyncing
            ? OmiColors.textPrimary
            : hasPendingOnDevice
                ? OmiColors.warning
                : OmiColors.textSecondary,
      ),
    );
  }
}
