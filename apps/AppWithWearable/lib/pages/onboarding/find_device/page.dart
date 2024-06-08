import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/utils/ble/scan.dart';
import 'package:friend_private/widgets/scanning_animation.dart';
import 'package:friend_private/widgets/scanning_ui.dart';

class FindDevicesPage extends StatefulWidget {
  const FindDevicesPage({super.key});

  @override
  _FindDevicesPageState createState() => _FindDevicesPageState();
}

class _FindDevicesPageState extends State<FindDevicesPage> with SingleTickerProviderStateMixin {
  BTDeviceStruct? _friendDevice;
  String _stringStatus1 = 'Looking for Friend wearable';
  String _stringStatus2 = 'Locating your Friend device. Keep it near your phone for pairing';
  bool _isConnected = false;

  @override
  void initState() {
    super.initState();
    SchedulerBinding.instance.addPostFrameCallback((_) {
      _scanDevices();
    });
  }

  Future<void> _scanDevices() async {
    // TODO: validate bluetooth turned on=
    BTDeviceStruct? friendDevice = await scanAndConnectDevice();
    if (friendDevice != null) {
      setState(() {
        _isConnected = true;
        _friendDevice = friendDevice;
        _stringStatus1 = 'Friend Wearable';
        _stringStatus2 = 'Successfully connected and ready to accelerate your journey with AI';
      });
    }
  }

  void _navigateToConnecting() async {
    if (_friendDevice == null) return;
    SharedPreferencesUtil().onboardingCompleted = true;
    MixpanelManager().onboardingCompleted();
    Navigator.of(context)
        .pushReplacement(MaterialPageRoute(builder: (c) => HomePageWrapper(btDevice: _friendDevice!.toJson())));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: SafeArea(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            const Padding(
              padding: EdgeInsets.only(top: 16.0),
              child: Text(
                'Pairing',
                style: TextStyle(
                  fontFamily: 'SF Pro Display',
                  color: Colors.white,
                  fontSize: 30.0,
                  letterSpacing: 0.0,
                  fontWeight: FontWeight.w700,
                  // useGoogleFonts: GoogleFonts.asMap().containsKey('SF Pro Display'),
                  height: 1.2,
                ),
                textAlign: TextAlign.center,
              ),
            ),
            const SizedBox(height: 16.0),
            AnimatedOpacity(
              duration: const Duration(milliseconds: 500),
              opacity: _isConnected ? 1.0 : 0.0,
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 8.0, horizontal: 32.0),
                child: Container(
                  decoration: BoxDecoration(
                    color: Colors.transparent,
                    borderRadius: BorderRadius.circular(30),
                    border: Border.all(
                      color: Colors.white,
                      width: 2,
                    ),
                  ),
                  padding: const EdgeInsets.all(8.0),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 10,
                        height: 10,
                        decoration: const BoxDecoration(
                          color: Color.fromARGB(255, 0, 255, 8),
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 8.0),
                      const Text(
                        'Friend Connected',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(height: 16.0),
            Expanded(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const ScanningAnimation(),
                  const SizedBox(height: 16.0),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 30.0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.center,
                      children: [
                        ScanningUI(
                          string1: _stringStatus1,
                          string2: _stringStatus2,
                        ),
                        AnimatedOpacity(
                          duration: const Duration(milliseconds: 500),
                          opacity: _isConnected ? 1.0 : 0.0,
                          child: Padding(
                            padding: const EdgeInsets.all(16.0),
                            child: MaterialButton(
                              onPressed: _navigateToConnecting,
                              height: 50,
                              padding: const EdgeInsets.symmetric(horizontal: 30),
                              color: Colors.white,
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
                              child: const Text(
                                'Continue',
                                style: TextStyle(fontSize: 20, color: Colors.black),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
