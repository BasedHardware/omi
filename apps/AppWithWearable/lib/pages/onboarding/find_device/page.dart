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
    var size = MediaQuery.of(context).size; // obtain MediaQuery data
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: SafeArea(
        child: Container(
          height: size.height, // Make the container take up the full height
          padding:
              const EdgeInsets.symmetric(horizontal: 32), // Responsive padding
          child: Column(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              HeaderSection(
                onBack: () => Navigator.of(context).pop(),
                onHelp: _launchURL,
              ),
              deviceList.isEmpty
                  ? SearchingSection(enableInstructions: enableInstructions)
                  : FoundDevices(deviceList: deviceList),
            ],
          ),
        ),
      ),
    );
  }
}

class HeaderSection extends StatelessWidget {
  final VoidCallback onBack;
  final VoidCallback onHelp;

  const HeaderSection({Key? key, required this.onBack, required this.onHelp})
      : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(0, 15, 0, 47),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          InkWell(
            onTap: onBack,
            child: SvgPicture.asset(
              'assets/images/backbutton.svg',
              width: 24,
              height: 24,
            ),
          ),
          Opacity(
            opacity: 0.8,
            child: InkWell(
              onTap: onHelp,
              child: Container(
                padding: const EdgeInsets.all(8), // Consistent paddings
                decoration: BoxDecoration(
                  border: Border.all(color: const Color(0xFFE4E4E2)),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Text(
                  'HELP',
                ),
              ),
            ),
          ),
        ],
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
    return Expanded(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Padding(
            padding: EdgeInsets.only(bottom: 12),
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
