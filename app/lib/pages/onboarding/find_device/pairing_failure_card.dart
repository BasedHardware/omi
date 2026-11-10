import 'package:flutter/material.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/l10n_extensions.dart';

String pairingFailureCopy(AppLocalizations l10n, DeviceConnectFailureShownFailureReason reason) => switch (reason) {
      DeviceConnectFailureShownFailureReason.bluetoothOff => l10n.pairingBluetoothOff,
      DeviceConnectFailureShownFailureReason.bluetoothPermissionDenied => l10n.pairingBluetoothPermission,
      DeviceConnectFailureShownFailureReason.nearbyDevicesDenied => l10n.pairingNearbyPermission,
      DeviceConnectFailureShownFailureReason.locationPermissionMissing => l10n.pairingLocationPermission,
      DeviceConnectFailureShownFailureReason.notFoundOrDropped => l10n.pairingNotFoundOrDropped,
      DeviceConnectFailureShownFailureReason.staleBond => l10n.pairingBondRecovery,
      DeviceConnectFailureShownFailureReason.unknown => l10n.anErrorOccurredTryAgain,
    };

/// Inline recovery stays beside discovery and does not expire like a toast.
/// Emit after the first displayed frame, once per presentation/reason.
class PairingFailureCard extends StatefulWidget {
  const PairingFailureCard(
      {super.key, required this.reason, required this.onDismiss, required this.onGuide, this.onRetry, this.emit});
  final DeviceConnectFailureShownFailureReason reason;
  final VoidCallback onDismiss;
  final VoidCallback onGuide;
  final Future<void> Function()? onRetry;
  final void Function(RegisteredEvent)? emit;

  @override
  State<PairingFailureCard> createState() => _PairingFailureCardState();
}

class _PairingFailureCardState extends State<PairingFailureCard> {
  @override
  void initState() {
    super.initState();
    _recordShown();
  }

  @override
  void didUpdateWidget(PairingFailureCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.reason != widget.reason) _recordShown();
  }

  void _recordShown() {
    final reason = widget.reason;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || widget.reason != reason) return;
      final platform = switch (Theme.of(context).platform) {
        TargetPlatform.iOS => DeviceConnectFailureShownPlatform.ios,
        TargetPlatform.android => DeviceConnectFailureShownPlatform.android,
        _ => DeviceConnectFailureShownPlatform.other,
      };
      (widget.emit ?? const TypedEvents().emit)(DeviceConnectFailureShown(failureReason: reason, platform: platform));
    });
  }

  @override
  Widget build(BuildContext context) => Material(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.lgAll,
        child: Padding(
          padding: const EdgeInsets.all(OmiSpacing.md),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, mainAxisSize: MainAxisSize.min, children: [
            Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Padding(
                padding: const EdgeInsets.only(top: OmiSpacing.sm),
                child: ExcludeSemantics(child: Icon(Icons.error_outline, color: OmiColors.danger)),
              ),
              const SizedBox(width: OmiSpacing.sm),
              Expanded(
                child: Semantics(
                  liveRegion: true,
                  child: Text(pairingFailureCopy(context.l10n, widget.reason), style: OmiType.body),
                ),
              ),
              OmiCloseButton(
                key: const Key('pairing_failure_dismiss'),
                color: OmiColors.textPrimary,
                onPressed: widget.onDismiss,
              ),
            ]),
            const SizedBox(height: OmiSpacing.sm),
            if (widget.onRetry != null) ...[
              OmiButton(
                  key: const Key('pairing_failure_retry'),
                  labelStyle: OmiType.callout.copyWith(
                      fontWeight: FontWeight.w600, fontFamily: Theme.of(context).textTheme.labelLarge?.fontFamily),
                  label: context.l10n.tryAgain,
                  onPressed: widget.onRetry,
                  expand: true),
              const SizedBox(height: OmiSpacing.sm),
            ],
            OmiButton(
              variant: OmiButtonVariant.secondary,
              labelStyle: OmiType.callout.copyWith(
                  fontWeight: FontWeight.w600, fontFamily: Theme.of(context).textTheme.labelLarge?.fontFamily),
              key: const Key('pairing_failure_guide'),
              label: context.l10n.pairingHowTo,
              onPressed: widget.onGuide,
              expand: true,
            ),
          ]),
        ),
      );
}
