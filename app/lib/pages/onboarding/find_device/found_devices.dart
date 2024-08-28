import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/providers/onboarding_provider.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:provider/provider.dart';

class FoundDevices extends StatefulWidget {
  final List<BTDeviceStruct> deviceList;
  final VoidCallback goNext;

  const FoundDevices({
    super.key,
    required this.deviceList,
    required this.goNext,
  });

  @override
  State<FoundDevices> createState() => _FoundDevicesState();
}

class _FoundDevicesState extends State<FoundDevices> {
  @override
  void initState() {
    //TODO: Already we have a listner in DeviceProvider, so we can remove this
    // _initiateConnectionListener();
    super.initState();
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
            Navigator.of(context).pushAndRemoveUntil(
              MaterialPageRoute(
                builder: (context) => const HomePageWrapper(),
              ),
              (route) => false,
            );
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
                    widget.deviceList.isEmpty
                        ? 'Searching for devices...'
                        : '${widget.deviceList.length} ${widget.deviceList.length == 1 ? "DEVICE" : "DEVICES"} FOUND NEARBY',
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
            if (widget.deviceList.isNotEmpty) const SizedBox(height: 16),
            if (!provider.isConnected) ..._devicesList(provider),
            if (provider.isConnected)
              Text(
                '${provider.deviceName} (${BTDeviceStruct.shortId(provider.deviceId)})',
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
    return (widget.deviceList.mapIndexed(
      (index, device) {
        bool isConnecting = provider.connectingToDeviceId == device.id;

        return GestureDetector(
          onTap: !provider.isClicked
              ? () async {
                  await provider.handleTap(
                    device: device,
                  );
                }
              : null,
          child: Container(
              margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
              decoration: BoxDecoration(
                border: const GradientBoxBorder(
                  gradient: LinearGradient(colors: [
                    Color.fromARGB(127, 208, 208, 208),
                    Color.fromARGB(127, 188, 99, 121),
                    Color.fromARGB(127, 86, 101, 182),
                    Color.fromARGB(127, 126, 190, 236)
                  ]),
                  width: 1,
                ),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.all(16.0),
                      child: Stack(
                        children: [
                          Align(
                            alignment: Alignment.center,
                            child: Text(
                              '${device.name} (${device.getShortId()})',
                              textAlign: TextAlign.center,
                              style: const TextStyle(
                                fontWeight: FontWeight.w500,
                                fontSize: 18,
                                color: Color(0xCCFFFFFF),
                              ),
                            ),
                          ),
                          Align(
                            alignment: Alignment.centerRight,
                            child: isConnecting
                                ? const SizedBox(
                                    height: 20,
                                    width: 20,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                    ),
                                  )
                                : const SizedBox.shrink(), // Show loading indicator if connecting
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
