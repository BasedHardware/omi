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

DevicePairingSettingsOpenedFailureReason? _settingsReason(DeviceConnectFailureShownFailureReason reason) =>
    switch (reason) {
      DeviceConnectFailureShownFailureReason.bluetoothPermissionDenied =>
        DevicePairingSettingsOpenedFailureReason.bluetoothPermissionDenied,
      DeviceConnectFailureShownFailureReason.nearbyDevicesDenied =>
        DevicePairingSettingsOpenedFailureReason.nearbyDevicesDenied,
      _ => null,
    };

/// Inline recovery stays beside discovery and does not expire like a toast.
/// Emit after the first displayed frame, once per presentation/reason.
class PairingFailureCard extends StatefulWidget {
  const PairingFailureCard(
      {super.key,
      required this.reason,
      required this.onDismiss,
      required this.onGuide,
      this.onRetry,
      this.onOpenSettings,
      this.emit});
  final DeviceConnectFailureShownFailureReason reason;
  final VoidCallback onDismiss;
  final VoidCallback onGuide;
  final Future<void> Function()? onRetry;

  /// Opens this app's page in system Settings. Only a Bluetooth or Nearby devices permission block
  /// shows it, as the primary action, with Try Again under it.
  final Future<void> Function()? onOpenSettings;
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

  Future<void> _openSettings(DevicePairingSettingsOpenedFailureReason reason) async {
    final platform = switch (Theme.of(context).platform) {
      TargetPlatform.iOS => DevicePairingSettingsOpenedPlatform.ios,
      TargetPlatform.android => DevicePairingSettingsOpenedPlatform.android,
      _ => DevicePairingSettingsOpenedPlatform.other,
    };
    (widget.emit ?? const TypedEvents().emit)(DevicePairingSettingsOpened(failureReason: reason, platform: platform));
    await widget.onOpenSettings!();
  }

  @override
  Widget build(BuildContext context) {
    final settingsReason = widget.onOpenSettings == null ? null : _settingsReason(widget.reason);
    final labelStyle = OmiType.callout
        .copyWith(fontWeight: FontWeight.w600, fontFamily: Theme.of(context).textTheme.labelLarge?.fontFamily);
    return Material(
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
          if (settingsReason != null) ...[
            OmiButton(
                key: const Key('pairing_failure_open_settings'),
                labelStyle: labelStyle,
                label: context.l10n.openSettings,
                onPressed: () => _openSettings(settingsReason),
                expand: true),
            const SizedBox(height: OmiSpacing.sm),
          ],
          if (widget.onRetry != null) ...[
            OmiButton(
                key: const Key('pairing_failure_retry'),
                variant: settingsReason == null ? OmiButtonVariant.primary : OmiButtonVariant.secondary,
                labelStyle: labelStyle,
                label: context.l10n.tryAgain,
                onPressed: widget.onRetry,
                expand: true),
            const SizedBox(height: OmiSpacing.sm),
          ],
          OmiButton(
            variant: OmiButtonVariant.secondary,
            labelStyle: labelStyle,
            key: const Key('pairing_failure_guide'),
            label: context.l10n.pairingHowTo,
            onPressed: widget.onGuide,
            expand: true,
          ),
        ]),
      ),
    );
  }
}
