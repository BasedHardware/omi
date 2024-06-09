import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';
import 'dart:io';
import 'package:friend_private/pages/onboarding/find_device/page.dart';
import 'package:permission_handler/permission_handler.dart';

class WelcomePage extends StatefulWidget {
  const WelcomePage({super.key});

  @override
  State<WelcomePage> createState() => _WelcomePageState();
}

class _WelcomePageState extends State<WelcomePage>
    with SingleTickerProviderStateMixin {
  final scaffoldKey = GlobalKey<ScaffoldState>();

  @override
  void initState() {
    super.initState();
    // Hide the status bar
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.manual, overlays: []);
  }

  @override
  void dispose() {
    // Show the status bar again when the widget is disposed
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.manual,
        overlays: SystemUiOverlay.values);
    super.dispose();
  }

  void _launchUrl(String _url) async {
    if (!await launch(_url)) throw 'Could not launch $_url';
  }

  @override
  Widget build(BuildContext context) {
    // Get the size of the screen for responsiveness
    var screenSize = MediaQuery.of(context).size;
    // Calculate the padding from the bottom based on the screen height for responsiveness
    double bottomPadding = screenSize.height * 0.2;

    return Scaffold(
      key: scaffoldKey,
      body: Container(
        decoration: const BoxDecoration(
          image: DecorationImage(
            image: AssetImage("assets/images/background.png"),
            fit: BoxFit.cover,
          ),
        ),
        child: Stack(
          children: [
            Padding(
              padding: EdgeInsets.only(
                bottom: 100,
              ),
              child: Center(
                // Tradeoff: SVG Export doesn't support drop shadows, and png isn't very sharp
                child: Image.asset("assets/images/herologo.png"),
              ),
            ),
            Column(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                Padding(
                  padding: EdgeInsets.only(
                    bottom: 10, // Padding from the bottom for the button
                    left:
                        screenSize.width * 0.1, // Horizontal padding for button
                    right: screenSize.width * 0.1,
                  ),
                  child: ElevatedButton(
                    onPressed: () async {
                      bool permissionsAccepted = false;
                      if (Platform.isIOS) {
                        PermissionStatus bleStatus =
                            await Permission.bluetooth.request();
                        debugPrint('bleStatus: $bleStatus');
                        permissionsAccepted = bleStatus.isGranted;
                        // TODO: apparently only needed for ios?
                      } else {
                        PermissionStatus bleScanStatus =
                            await Permission.bluetoothScan.request();
                        PermissionStatus bleConnectStatus =
                            await Permission.bluetoothConnect.request();
                        // PermissionStatus locationStatus = await Permission.location.request();

                        permissionsAccepted = bleConnectStatus.isGranted &&
                            bleScanStatus
                                .isGranted; // && locationStatus.isGranted;

                        debugPrint(
                            'bleScanStatus: $bleScanStatus ~ bleConnectStatus: $bleConnectStatus');
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
                        Navigator.of(context).push(MaterialPageRoute(
                            builder: (c) => const FindDevicesPage()));
                      }
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.white, // Button color
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    child: Container(
                      width: double
                          .infinity, // Button takes full width of the padding
                      height: 45, // Fixed height for the button
                      child: Center(
                        child: Text(
                          'Connect Your Wearable',
                          style: TextStyle(
                              fontWeight: FontWeight.w600,
                              fontSize: screenSize.width * 0.041,
                              color: Colors.black),
                        ),
                      ),
                    ),
                  ),
                ),
                RichText(
                  textAlign: TextAlign.center,
                  text: TextSpan(
                    style: TextStyle(
                      color: Colors.white, // Text color
                      fontSize:
                          screenSize.width * 0.025, // Responsive font size
                    ),
                    children: [
                      const TextSpan(
                          text: 'By tapping on "Connect", you agree to our\n'),
                      TextSpan(
                        text: 'Terms of service',
                        style: const TextStyle(
                          decoration: TextDecoration.underline,
                        ),
                        //To be changed later with basedhardware.com/Termsofservice
                        recognizer: TapGestureRecognizer()
                          ..onTap = () {
                            _launchUrl(
                                'https://samaprivacypolicy.notion.site/samaprivacypolicy/Sama-AI-Privacy-Policy-bfbbee90f18d4b8b9a0111d2d62cca54');
                          },
                      ),
                      const TextSpan(text: ' and '),
                      TextSpan(
                        text: 'Privacy Policy',
                        style: const TextStyle(
                          decoration: TextDecoration.underline,
                        ),
                        //To be changed later with basedhardware.com/PrivacyPolicy
                        recognizer: TapGestureRecognizer()
                          ..onTap = () {
                            _launchUrl(
                                'https://samaprivacypolicy.notion.site/samaprivacypolicy/Sama-AI-Privacy-Policy-bfbbee90f18d4b8b9a0111d2d62cca54');
                          },
                      ),
                    ],
                  ),
                ),
                SizedBox(
                    height: bottomPadding *
                        0.5), // Padding from bottom for the text
              ],
            ),
          ],
        ),
      ),
    );
  }
}
