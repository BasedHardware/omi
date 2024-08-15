import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:permission_handler/permission_handler.dart';

class WelcomePage extends StatefulWidget {
  final VoidCallback goNext;
  final VoidCallback skipDevice;

  const WelcomePage({super.key, required this.goNext, required this.skipDevice});

  @override
  State<WelcomePage> createState() => _WelcomePageState();
}

class _WelcomePageState extends State<WelcomePage> with SingleTickerProviderStateMixin {
  @override
  void initState() {
    super.initState();
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.manual, overlays: []);
  }

  @override
  void dispose() {
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.manual, overlays: SystemUiOverlay.values);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Get the size of the screen for responsiveness
    var screenSize = MediaQuery.of(context).size;
    // Calculate the padding from the bottom based on the screen height for responsiveness

    return Column(
      mainAxisAlignment: MainAxisAlignment.end,
      children: [
        Padding(
          padding: EdgeInsets.only(left: screenSize.width * 0.1, right: screenSize.width * 0.1),
          child: Container(
            decoration: BoxDecoration(
              border: const GradientBoxBorder(
                gradient: LinearGradient(colors: [
                  Color.fromARGB(127, 208, 208, 208),
                  Color.fromARGB(127, 188, 99, 121),
                  Color.fromARGB(127, 86, 101, 182),
                  Color.fromARGB(127, 126, 190, 236)
                ]),
                width: 2,
              ),
              borderRadius: BorderRadius.circular(12),
            ),
            child: ElevatedButton(
              onPressed: () async {
                bool permissionsAccepted = false;
                if (Platform.isIOS) {
                  PermissionStatus bleStatus = await Permission.bluetooth.request();
                  debugPrint('bleStatus: $bleStatus');
                  permissionsAccepted = bleStatus.isGranted;
                } else {
                  PermissionStatus bleScanStatus = await Permission.bluetoothScan.request();
                  PermissionStatus bleConnectStatus = await Permission.bluetoothConnect.request();
                  // PermissionStatus locationStatus = await Permission.location.request();

                  permissionsAccepted =
                      bleConnectStatus.isGranted && bleScanStatus.isGranted; // && locationStatus.isGranted;

                  debugPrint('bleScanStatus: $bleScanStatus ~ bleConnectStatus: $bleConnectStatus');
                }
                if (!permissionsAccepted) {
                  showDialog(
                    context: context,
                    builder: (BuildContext context) {
                      return AlertDialog(
                        backgroundColor: Colors.grey[900],
                        title: const Text(
                          'Permissions Required',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 20,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        content: const Text(
                          'This app needs Bluetooth and Location permissions to function properly. Please enable them in the settings.',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 16,
                          ),
                        ),
                        actions: [
                          TextButton(
                            onPressed: () {
                              Navigator.of(context).pop();
                              openAppSettings();
                            },
                            child: const Text(
                              'OK',
                              style: TextStyle(
                                color: Colors.blue,
                                fontSize: 16,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                        ],
                      );
                    },
                  );
                } else {
                  widget.goNext();
                }
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.transparent,
                shadowColor: const Color.fromARGB(255, 17, 17, 17),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
              child: Container(
                width: double.infinity, // Button takes full width of the padding
                height: 45, // Fixed height for the button
                alignment: Alignment.center,
                child: const Text(
                  'Connect My Friend',
                  style: TextStyle(
                    fontWeight: FontWeight.w400,
                    fontSize: 18,
                    color: Color.fromARGB(255, 255, 255, 255),
                  ),
                ),
              ),
            ),
          ),
        ),
        TextButton(
            onPressed: () {
              widget.skipDevice();
              MixpanelManager().useWithoutDeviceOnboardingWelcome();
            },
            child: const Text(
              'Skip for now',
              style: TextStyle(
                  color: Colors.white,
                  // decoration: TextDecoration.underline,
                  fontSize: 14,
                  fontWeight: FontWeight.normal),
            )),
        const SizedBox(height: 16)
      ],
    );
  }
}
