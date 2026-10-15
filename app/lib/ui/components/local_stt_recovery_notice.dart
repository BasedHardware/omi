import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:omi/services/sockets/local_stt_failure.dart';
import 'package:omi/services/sockets/on_device_apple_provider.dart';
import 'package:omi/services/freemium_transcription_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// A local setup problem leaves capture and its WAL active. Reuses existing
/// fallback copy and offers permission/settings plus an explicit retained retry.
class LocalSttRecoveryNotice extends StatefulWidget {
  const LocalSttRecoveryNotice(
      {super.key,
      required this.failure,
      required this.onRetry,
      required this.onSetup,
      this.language,
      this.preparePermission,
      this.openSettings});
  final LocalSttFailure failure;
  final String? language;
  final Future<void> Function() onRetry;
  final VoidCallback onSetup;
  final Future<bool> Function()? preparePermission;
  final Future<bool> Function()? openSettings;
  @override
  State<LocalSttRecoveryNotice> createState() => _LocalSttRecoveryNoticeState();
}

class _LocalSttRecoveryNoticeState extends State<LocalSttRecoveryNotice> {
  bool _busy = false;
  Future<void> _retry() async {
    setState(() => _busy = true);
    try {
      await widget.onRetry();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _setup() async {
    if (widget.failure.code == 'permission_required') {
      final ready = await (widget.preparePermission ??
          () async => (await OnDeviceAppleProvider.readiness(
                  FreemiumTranscriptionService.effectiveLanguage(language: widget.language),
                  prepare: true))
              .ready)();
      if (ready) {
        await _retry();
        return;
      }
      await (widget.openSettings ?? openAppSettings)();
    } else if (widget.failure.code == 'permission_denied' || widget.failure.code == 'unauthorized') {
      await (widget.openSettings ?? openAppSettings)();
    } else {
      widget.onSetup();
    }
  }

  @override
  Widget build(BuildContext context) {
    final permission = widget.failure.code.startsWith('permission') || widget.failure.code == 'unauthorized';
    return Semantics(
        liveRegion: true,
        child: Padding(
          padding: const EdgeInsets.all(OmiSpacing.md),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(context.l10n.transcriptionUnavailableRecordingSaved, style: OmiType.footnote),
            const SizedBox(height: OmiSpacing.sm),
            Wrap(spacing: OmiSpacing.sm, runSpacing: OmiSpacing.sm, children: [
              OmiButton.secondary(
                  key: const ValueKey('local_stt_setup'),
                  label: permission ? context.l10n.openSettings : context.l10n.setupOnDevice,
                  onPressed: _busy ? null : _setup),
              OmiButton.secondary(
                  key: const ValueKey('local_stt_retry'),
                  label: context.l10n.tryAgain,
                  onPressed: _busy ? null : _retry),
            ]),
          ]),
        ));
  }
}
