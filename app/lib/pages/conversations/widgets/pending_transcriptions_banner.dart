import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/conversations/sync_page.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// Compact banner on the conversations list while phone-local recordings are
/// still waiting to be uploaded for transcription — the backlog a transcription
/// outage or an offline capture leaves behind. Tapping opens the sync surface
/// that drains it. Hides itself once the backlog is empty.
class PendingTranscriptionsBanner extends StatelessWidget {
  const PendingTranscriptionsBanner({super.key});

  /// [Provider.of] for a provider the page can live without (hermetic fixtures
  /// embed the conversations page without one), same idiom as device settings.
  SyncProvider? _maybeProvider(BuildContext context) {
    try {
      return Provider.of<SyncProvider>(context);
    } on ProviderNotFoundException {
      return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final syncProvider = _maybeProvider(context);
    if (syncProvider == null) return const SizedBox.shrink();
    final pendingCount = syncProvider.pendingLocalTranscriptionWals.length;
    if (pendingCount == 0) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
      child: Semantics(
        button: true,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () {
            final deviceProvider = context.read<DeviceProvider>();
            routeToPage(
              context,
              deviceProvider.supportsMultiFileSync ? const AutoSyncPage() : const SyncPage(),
            );
          },
          child: Container(
            key: const Key('pending_transcriptions_banner'),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: OmiColors.surface1,
              borderRadius: const BorderRadius.all(Radius.circular(OmiRadius.md)),
              border: Border.all(color: OmiColors.border, width: 0.5),
            ),
            child: Row(
              children: [
                const Icon(Icons.cloud_upload_outlined, size: 16, color: OmiColors.textSecondary),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    context.l10n.transcriptionsPendingCount(pendingCount),
                    style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
                  ),
                ),
                const Icon(Icons.chevron_right, size: 16, color: OmiColors.textTertiary),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
