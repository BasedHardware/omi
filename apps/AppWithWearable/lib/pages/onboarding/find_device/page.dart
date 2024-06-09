import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/utils/ble/scan.dart';
import 'found_devices.dart';

class FindDevicesPage extends StatefulWidget {
  const FindDevicesPage({Key? key}) : super(key: key);

  @override
  _FindDevicesPageState createState() => _FindDevicesPageState();
}

class _FindDevicesPageState extends State<FindDevicesPage>
    with SingleTickerProviderStateMixin {
  List<BTDeviceStruct?> deviceList = [];
  bool enableInstructions = false;

  @override
  void initState() {
    super.initState();
    SchedulerBinding.instance.addPostFrameCallback((_) {
      _scanDevices();
    });
  }

  Future<void> _scanDevices() async {
    // TODO: validate bluetooth turned on
    bool didMakeIt =
        false; // a flag to indicate if devices are found within 10 seconds
    bool cancelTimer = false;
    bool timerIsActive = true;
    Timer didNotMakeItTimer = Timer(const Duration(seconds: 10), () {
      if (!didMakeIt) {
        cancelTimer = true;
        setState(() {
          enableInstructions = true;
        });
      }
    });
    while (true) {
      List<BTDeviceStruct?> foundDevices = await scanDevices();
      if (foundDevices.isNotEmpty) {
        didMakeIt = true;
        setState(() {
          deviceList = foundDevices;
        });
      }

      // Cancel the instructions timer after first trigger
      if (cancelTimer && timerIsActive) {
        timerIsActive = false;
        didNotMakeItTimer.cancel();
      }

      await Future.delayed(const Duration(seconds: 2));
    }
  }

  void _launchURL() async {
    const url =
        'https://discord.com/servers/based-hardware-1192313062041067520';
    if (!await launch(url)) throw 'Could not launch $url';
  }

  @override
  Widget build(BuildContext context) {
    var screenSize = MediaQuery.of(context).size;
    var size = MediaQuery.of(context).size; // obtain MediaQuery data
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: SafeArea(
        child: Container(
          height: size.height, // Make the container take up the full height
          padding:
              const EdgeInsets.symmetric(horizontal: 32, vertical: 0), // Responsive padding
          child: Column(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              deviceList.isEmpty
                  ? SearchingSection(enableInstructions: enableInstructions)
                  : FoundDevices(deviceList: deviceList),
                deviceList.isEmpty ? enableInstructions ?                 Padding(
                  padding: EdgeInsets.only(
                    bottom: 20, // Padding from the bottom for the button
                    left:
                        screenSize.width * 0.0, // Horizontal padding for button
                    right: screenSize.width * 0.0,
                  ),
                  child:                 Padding(
                  padding: EdgeInsets.only(
                    bottom: 10, // Padding from the bottom for the button
                    left:
                        screenSize.width * 0.0, // Horizontal padding for button
                    right: screenSize.width * 0.0,
                  ),
                  child: Container(
                    decoration: BoxDecoration(
                      border: Border.all(color: Color.fromARGB(255, 55, 55, 55), width : 2.0),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: ElevatedButton(
                      onPressed: () {
                        _launchURL();
                      },
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.transparent,
                        shadowColor: const Color.fromARGB(255, 17, 17, 17),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                      child: Container(
                        width: double
                            .infinity, // Button takes full width of the padding
                        height: 45, // Fixed height for the button
                        alignment: Alignment.center,
                        child: Text(
                          'Contact Support',
                          style: TextStyle(
                              fontWeight: FontWeight.w400,
                              fontSize: screenSize.width * 0.045,
                              color: const Color.fromARGB(255, 55, 55, 55)),
                        ),
                      ),
                    ),
                  ), )
                ) : SizedBox.shrink() :  SizedBox.shrink()
            ],
          ),
        ),
      ),
    );
  }
}


class SearchingSection extends StatelessWidget {
  final bool enableInstructions;

  const SearchingSection({
    Key? key,
    required this.enableInstructions,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    var screenSize = MediaQuery.of(context).size;
    return Expanded(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
           Padding(
            padding: EdgeInsets.only(bottom: 12, top: screenSize.height * 0.08),
            child: Text(
              'SEARCHING FOR DEVICE...',
              style: TextStyle(
                color: Color.fromARGB(255, 255, 255, 255),
                fontSize: 17,
                fontWeight: FontWeight.normal,
              ),
            ),
          ),
          if (enableInstructions)
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 10.0),
              child: Text(
                "Check if your device is charged by double tapping the top. A green light should be blinking on the side if it's charged.",
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Color.fromARGB(127, 255, 255, 255),
                  fontSize: 12,
                  fontWeight: FontWeight.normal,
                ),
              ),
            ),
          const Spacer(),
          Center(
            child: Image.asset(
              "assets/images/searching.png",
              width: MediaQuery.of(context).size.width * 0.9,
            ),
          ),
          const Spacer(),
        ],
      ),
    );
  }
}
