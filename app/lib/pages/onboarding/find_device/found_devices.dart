import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/onboarding/apple_watch_permission_page.dart';
import 'package:omi/widgets/apple_watch_setup_bottom_sheet.dart';
import 'package:omi/services/devices/apple_watch_connection.dart';
import 'package:omi/services/services.dart';
import 'package:omi/src/flutter_communicator.g.dart';
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

  String _getDeviceImagePath(String deviceName) {
    if (deviceName.contains('Glass')) {
      return Assets.images.omiGlass.path;
    }
    if (deviceName.contains('Omi DevKit')) {
      return Assets.images.omiDevkitWithoutRope.path;
    }
    if (deviceName.contains('Apple Watch')) {
      return Assets.images.appleWatch.path;
    }
    return Assets.images.omiWithoutRope.path;
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
        // Permission not granted - show permission page
        await _showMicrophonePermissionPage(connection);
      } else {
        // Recording started successfully - complete the onboarding
        await _completeAppleWatchOnboarding(device, provider);
      }
    } catch (e) {
      debugPrint('Error handling Apple Watch onboarding: $e');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error connecting to Apple Watch: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  /// Show bottom sheet when Apple Watch is not reachable
  Future<void> _showWatchNotReachableBottomSheet(String deviceId) async {
    await showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => AppleWatchSetupBottomSheet(
        deviceId: deviceId,
        onConnected: () async {
          // Retry the connection flow when user says they've connected
          final device =
              Provider.of<OnboardingProvider>(context, listen: false).deviceList.firstWhere((d) => d.id == deviceId);
          final provider = Provider.of<OnboardingProvider>(context, listen: false);
          await _handleAppleWatchOnboarding(device, provider);
        },
      ),
    );
  }

  /// Show permission page when microphone permission is needed
  Future<void> _showMicrophonePermissionPage(AppleWatchDeviceConnection connection) async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (context) => AppleWatchPermissionPage(
          connection: connection,
          onPermissionGranted: () async {
            // Permission granted and recording started - complete onboarding
            final provider = Provider.of<OnboardingProvider>(context, listen: false);
            final device = provider.deviceList.firstWhere((d) => d.id == connection.device.id);
            await _completeAppleWatchOnboarding(device, provider);
          },
        ),
      ),
    );
  }

  /// Complete Apple Watch onboarding after successful connection and recording
  Future<void> _completeAppleWatchOnboarding(BtDevice device, OnboardingProvider provider) async {
    try {
      // Set device as connected in provider
      provider.deviceId = device.id;
      provider.deviceName = device.name;
      provider.isConnected = true;
      provider.isClicked = false;
      provider.connectingToDeviceId = null;

      // Save device preferences
      await provider.deviceProvider?.scanAndConnectToDevice();

      // Complete the onboarding flow
      if (widget.isFromOnboarding) {
        widget.goNext();
      } else {
        Navigator.pop(context);
      }
    } catch (e) {
      debugPrint('Error completing Apple Watch onboarding: $e');
    }
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
            Navigator.pop(context);
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
                        ? 'Searching for devices...'
                        : '${provider.deviceList.length} ${provider.deviceList.length == 1 ? "DEVICE" : "DEVICES"} FOUND NEARBY',
                    style: const TextStyle(
                      fontWeight: FontWeight.w400,
                      fontSize: 14,
                      color: Color(0x66FFFFFF),
                    ),
                  )
                : const Text(
                    'PAIRING SUCCESSFUL',
                    style: TextStyle(
                      fontWeight: FontWeight.w400,
                      fontSize: 12,
                      color: Color(0x66FFFFFF),
                    ),
                  ),
            if (provider.deviceList.isNotEmpty) const SizedBox(height: 16),
            if (!provider.isConnected) ..._devicesList(provider),
            if (provider.isConnected)
              Text(
                '${provider.deviceName} (${BtDevice.shortId(provider.deviceId)})',
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
                      _getDeviceImagePath(device.name),
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
                              '${device.name} (${device.getShortId()})',
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
