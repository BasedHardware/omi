import 'package:flutter/material.dart';

import 'package:collection/collection.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/pages/onboarding/find_device/device_discovery_controller.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

@visibleForTesting
Future<void> retryOfflineSavedDevice(Future<void> Function() connect) => connect();

class FoundDevices extends StatefulWidget {
  final bool isFromOnboarding;
  final VoidCallback goNext;

  const FoundDevices({
    super.key,
    required this.goNext,
    required this.isFromOnboarding,
    this.onRescan,
    this.showStatus = true,
  });

  /// Draws the "Searching for devices" / "N devices found" line. Off once a scan has ended with
  /// nothing found, where the page shows its own empty state instead.
  final bool showStatus;

  /// Scans again; offered on an offline saved device's "Try Again".
  final Future<void> Function()? onRescan;

  @override
  State<FoundDevices> createState() => _FoundDevicesState();
}

class _FoundDevicesState extends State<FoundDevices> {
  late final DeviceDiscoveryController _discovery;

  @override
  void initState() {
    super.initState();
    _discovery = DeviceDiscoveryController(
      context: context,
      isFromOnboarding: widget.isFromOnboarding,
      goNext: widget.goNext,
      onRescan: widget.onRescan,
    );
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (mounted) {
        context.read<DeviceProvider>().initiateConnection('FoundDevices');
      }
    });
  }

  @override
  void didUpdateWidget(FoundDevices oldWidget) {
    super.didUpdateWidget(oldWidget);
    _discovery
      ..isFromOnboarding = widget.isFromOnboarding
      ..goNext = widget.goNext
      ..onRescan = widget.onRescan;
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<OnboardingProvider>(
      builder: (context, provider, child) {
        final visibleDevices = provider.visibleDeviceList;
        return MessageListener<OnboardingProvider>(
          showError: (error) => OmiFeedback.error(context, error),
          showInfo: (info) {
            if (info == "DEVICE_CONNECTED") {
              // Navigator.of(context).pushAndRemoveUntil(
              //   MaterialPageRoute(
              //     builder: (context) => const HomePageWrapper(),
              //   ),
              //   (route) => false,
              // );
              if (mounted) Navigator.pop(context);
            } else {
              OmiFeedback.info(context, info);
            }
          },
          child: Column(
            mainAxisAlignment: MainAxisAlignment.start,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              if (!widget.showStatus && !provider.isConnected)
                const SizedBox.shrink()
              else if (!provider.isConnected)
                Text(
                  provider.nearbyDeviceCount == 0
                      ? context.l10n.searchingForDevices
                      : context.l10n.devicesFoundNearby(provider.nearbyDeviceCount),
                  style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                )
              else
                Text(context.l10n.pairingSuccessful, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
              if (visibleDevices.isNotEmpty) const SizedBox(height: 16),
              if (!provider.isConnected) ..._devicesList(provider),
              if (provider.isConnected)
                Text(
                  discoveryDeviceLabel(provider, provider.deviceName, provider.deviceId),
                  textAlign: TextAlign.center,
                  style: OmiType.body.copyWith(fontWeight: FontWeight.w500),
                ),
              if (provider.isConnected && provider.batteryPercentage > 0)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  child: Semantics(
                    label: context.l10n.batteryLevelSemantics(provider.batteryPercentage),
                    excludeSemantics: true,
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          provider.batteryPercentage <= 25 ? Icons.battery_alert : Icons.battery_std,
                          size: 20,
                          color: provider.batteryPercentage <= 25 ? OmiColors.danger : OmiColors.textSecondary,
                        ),
                        const SizedBox(width: OmiSpacing.xxs),
                        Text(
                          '${provider.batteryPercentage}%',
                          style: OmiType.body.copyWith(fontWeight: FontWeight.w500),
                        ),
                      ],
                    ),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }

  _devicesList(OnboardingProvider provider) {
    return (provider.visibleDeviceList.mapIndexed((index, device) {
      bool isConnecting = provider.connectingToDeviceId == device.id;
      final isOfflineSavedDevice = provider.isSavedDevice(device) && !provider.isDeviceOnline(device);

      final label = discoveryDeviceLabel(provider, device.name, device.id);
      final onTap = !provider.isClicked ? () => _discovery.tap(device) : null;
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl, vertical: OmiSpacing.xs),
        child: Semantics(
          button: true,
          enabled: onTap != null,
          label: isOfflineSavedDevice ? '$label, ${context.l10n.offline}' : label,
          excludeSemantics: true,
          child: Material(
            color: OmiColors.accent,
            shape: const RoundedRectangleBorder(borderRadius: OmiRadius.lgAll),
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: onTap,
              child: Row(
                children: [
                  // Device icon
                  Padding(
                    padding: const EdgeInsets.all(16.0),
                    child: Image.asset(
                      DeviceUtils.getDeviceImagePath(
                        deviceType: device.type,
                        modelNumber: device.modelNumber,
                        deviceName: device.name,
                      ),
                      width: 32,
                      height: 32,
                    ),
                  ),
                  // Device name and info
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 16.0),
                      child: Row(
                        children: [
                          Expanded(
                            child: Text(
                              label,
                              textAlign: TextAlign.left,
                              overflow: TextOverflow.ellipsis,
                              style: OmiType.body.copyWith(fontWeight: FontWeight.w500, color: OmiColors.onAccent),
                            ),
                          ),
                          if (provider.isSavedDevice(device))
                            Container(
                              margin: const EdgeInsets.only(left: 8, right: 12),
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                              decoration: BoxDecoration(
                                color: OmiColors.onAccent.withValues(alpha: 0.08),
                                borderRadius: OmiRadius.smAll,
                              ),
                              child: Text(
                                isOfflineSavedDevice ? context.l10n.offline : context.l10n.saved,
                                style: OmiType.footnote.copyWith(
                                  fontWeight: FontWeight.w600,
                                  color: OmiColors.onAccent.withValues(alpha: 0.6),
                                ),
                              ),
                            ),
                          Padding(
                            padding: const EdgeInsets.only(right: 16.0),
                            child: isConnecting
                                ? OmiSpinner(size: OmiSpinnerSize.small, color: OmiColors.onAccent)
                                : const SizedBox.shrink(),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
    }).toList());
  }
}
