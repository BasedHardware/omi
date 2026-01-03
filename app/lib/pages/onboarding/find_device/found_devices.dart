import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/pages/onboarding/apple_watch_permission_page.dart';
import 'package:omi/widgets/apple_watch_setup_bottom_sheet.dart';
import 'package:omi/widgets/confirmation_dialog.dart';
import 'package:omi/services/devices/apple_watch_connection.dart';
import 'package:omi/services/services.dart';
import 'package:omi/gen/flutter_communicator.g.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:provider/provider.dart';

class FoundDevices extends StatefulWidget {
  final bool isFromOnboarding;
  final VoidCallback goNext;

  const FoundDevices({
    super.key,
    required this.goNext,
    required this.isFromOnboarding,
  });

  @override
  State<FoundDevices> createState() => _FoundDevicesState();
}

class _FoundDevicesState extends State<FoundDevices> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (mounted) {
        context.read<DeviceProvider>().periodicConnect('coming from FoundDevices');
      }
    });
  }

  Future<void> _handleAppleWatchOnboarding(BtDevice device, OnboardingProvider provider) async {
    try {
      // First check if the watch is reachable
      final hostAPI = WatchRecorderHostAPI();
      final bool isReachable = await hostAPI.isWatchReachable();

      if (!isReachable) {
        // Watch is not reachable - show bottom sheet to install/open app
        await _showWatchNotReachableBottomSheet(device.id);
        return;
      }

      // Watch is reachable - connect and check permissions
      await ServiceManager.instance().device.ensureConnection(device.id, force: true);
      final connection = await ServiceManager.instance().device.ensureConnection(device.id);

      if (connection is! AppleWatchDeviceConnection) {
        debugPrint('Device is not an Apple Watch connection');
        return;
      }

      // Check permission and try to start recording immediately
      final bool recordingStarted = await connection.checkPermissionAndStartRecording();

      if (!recordingStarted) {
        await _showMicrophonePermissionPage(connection);
        if (!mounted) return;
      } else {
        await _completeAppleWatchOnboarding(device, provider);
        if (!mounted) return;
      }
    } catch (e) {
      debugPrint('Error handling Apple Watch onboarding: $e');
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(context.l10n.errorConnectingAppleWatch(e.toString())),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  /// Show bottom sheet when Apple Watch is not reachable
  Future<void> _showWatchNotReachableBottomSheet(String deviceId) async {
    final provider = Provider.of<OnboardingProvider>(context, listen: false);
    final device = provider.deviceList.firstWhereOrNull((d) => d.id == deviceId);
    if (device == null) {
      debugPrint('Device with id $deviceId not found in provider list.');
      return;
    }

    await showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => AppleWatchSetupBottomSheet(
        deviceId: deviceId,
        onConnected: () async {
          await _handleAppleWatchOnboarding(device, provider);
        },
      ),
    );
  }

  Future<void> _showMicrophonePermissionPage(AppleWatchDeviceConnection connection) async {
    final provider = Provider.of<OnboardingProvider>(context, listen: false);
    final device = provider.deviceList.firstWhereOrNull((d) => d.id == connection.device.id);
    if (device == null) {
      debugPrint('Device with id ${connection.device.id} not found in provider list.');
      return;
    }

    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (context) => AppleWatchPermissionPage(
          connection: connection,
          onPermissionGranted: () async {
            await _completeAppleWatchOnboarding(device, provider);
          },
        ),
      ),
    );
    if (!mounted) return;
  }

  Future<void> _completeAppleWatchOnboarding(BtDevice device, OnboardingProvider provider) async {
    try {
      provider.deviceId = device.id;
      provider.deviceName = device.name;
      provider.isConnected = true;
      provider.isClicked = false;
      provider.connectingToDeviceId = null;

      await provider.deviceProvider?.scanAndConnectToDevice();

      if (!mounted) return;

      // Show firmware warning if needed
      await _showFirmwareWarningIfNeeded(device);

      if (!mounted) return;

      if (widget.isFromOnboarding) {
        widget.goNext();
      } else {
        if (mounted) Navigator.pop(context);
      }
    } catch (e) {
      debugPrint('Error completing Apple Watch onboarding: $e');
    }
  }

  Future<void> _showFirmwareWarningIfNeeded(BtDevice device) async {
    final warningMessage = device.getFirmwareWarningMessage();
    if (warningMessage.isEmpty) {
      return; // No warning needed for this device type
    }

    // Check if user has already acknowledged this device type
    final prefKey = 'firmware_warning_acknowledged_${device.type.toString()}';
    final alreadyAcknowledged = SharedPreferencesUtil().getBool(prefKey) ?? false;

    if (alreadyAcknowledged) {
      return; // User already acknowledged this warning
    }

    bool dontShowAgain = false;

    if (!mounted) return;

    await showDialog(
      context: context,
      barrierDismissible: false, // Must click button
      builder: (dialogContext) => ConfirmationDialog(
        title: device.getFirmwareWarningTitle(),
        description: warningMessage,
        checkboxText: context.l10n.dontShowAgain,
        checkboxValue: dontShowAgain,
        onCheckboxChanged: (value) {
          dontShowAgain = value;
        },
        confirmText: context.l10n.iUnderstand,
        onConfirm: () {
          if (dontShowAgain) {
            SharedPreferencesUtil().saveBool(prefKey, true);
          }
          Navigator.pop(dialogContext);
        },
        onCancel: () {
          // Not used, but required by ConfirmationDialog
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<OnboardingProvider>(builder: (context, provider, child) {
      return MessageListener<OnboardingProvider>(
        showError: (error) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(error),
            backgroundColor: Colors.red,
          ));
        },
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
            ScaffoldMessenger.of(context).showSnackBar(SnackBar(
              content: Text(info),
              backgroundColor: Colors.green,
            ));
          }
        },
        child: Column(
          mainAxisAlignment: MainAxisAlignment.start,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            !provider.isConnected
                ? Text(
                    provider.deviceList.isEmpty
                        ? context.l10n.searchingForDevices
                        : context.l10n.devicesFoundNearby(provider.deviceList.length),
                    style: const TextStyle(
                      fontWeight: FontWeight.w400,
                      fontSize: 14,
                      color: Color(0x66FFFFFF),
                    ),
                  )
                : Text(
                    context.l10n.pairingSuccessful,
                    style: const TextStyle(
                      fontWeight: FontWeight.w400,
                      fontSize: 12,
                      color: Color(0x66FFFFFF),
                    ),
                  ),
            if (provider.deviceList.isNotEmpty) const SizedBox(height: 16),
            if (!provider.isConnected) ..._devicesList(provider),
            if (provider.isConnected)
              Text(
                () {
                  final sameNameCount = provider.deviceList.where((d) => d.name == provider.deviceName).length;
                  return sameNameCount > 1
                      ? '${provider.deviceName} (${BtDevice.shortId(provider.deviceId)})'
                      : provider.deviceName;
                }(),
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontWeight: FontWeight.w500,
                  fontSize: 18,
                  color: Color(0xCCFFFFFF),
                ),
              ),
            if (provider.isConnected)
              Padding(
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  child: Text(
                    '🔋 ${provider.batteryPercentage.toString()}%',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontWeight: FontWeight.w500,
                      fontSize: 18,
                      color: provider.batteryPercentage <= 25
                          ? Colors.red
                          : provider.batteryPercentage > 25 && provider.batteryPercentage <= 50
                              ? Colors.orange
                              : Colors.green,
                    ),
                  ))
          ],
        ),
      );
    });
  }

  _devicesList(OnboardingProvider provider) {
    return (provider.deviceList.mapIndexed(
      (index, device) {
        bool isConnecting = provider.connectingToDeviceId == device.id;

        return GestureDetector(
          onTap: !provider.isClicked
              ? () async {
                  if (device.type == DeviceType.appleWatch) {
                    await _handleAppleWatchOnboarding(device, provider);
                  } else {
                    // Handle other devices
                    await provider.handleTap(
                      device: device,
                      isFromOnboarding: widget.isFromOnboarding,
                      goNext: widget.goNext,
                    );

                    if (!mounted) return;

                    // Show firmware warning after successful connection
                    if (provider.isConnected) {
                      await _showFirmwareWarningIfNeeded(device);
                    }
                  }
                }
              : null,
          child: Container(
              margin: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(18),
              ),
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
                      child: Stack(
                        children: [
                          Align(
                            alignment: Alignment.centerLeft,
                            child: Text(
                              () {
                                final sameNameCount = provider.deviceList.where((d) => d.name == device.name).length;
                                return sameNameCount > 1 ? '${device.name} (${device.getShortId()})' : device.name;
                              }(),
                              textAlign: TextAlign.left,
                              style: const TextStyle(
                                fontWeight: FontWeight.w500,
                                fontSize: 18,
                                color: Colors.black,
                              ),
                            ),
                          ),
                          Align(
                            alignment: Alignment.centerRight,
                            child: Padding(
                              padding: const EdgeInsets.only(right: 16.0),
                              child: isConnecting
                                  ? const SizedBox(
                                      height: 20,
                                      width: 20,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                        valueColor: AlwaysStoppedAnimation<Color>(Colors.black),
                                      ),
                                    )
                                  : const SizedBox.shrink(),
                            ),
                          )
                        ],
                      ),
                    ),
                  ),
                ],
              )),
        );
      },
    ).toList());
  }
}
