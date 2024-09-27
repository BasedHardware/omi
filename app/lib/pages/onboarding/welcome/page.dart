import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/providers/onboarding_provider.dart';
import 'package:friend_private/utils/analytics/intercom.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';

class WelcomePage extends StatefulWidget {
  final VoidCallback goNext;

  const WelcomePage({super.key, required this.goNext});

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
        Consumer<OnboardingProvider>(
          builder: (context, provider, child) {
            return Padding(
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
                    await provider.askForBluetoothPermissions();
                    if (provider.hasBluetoothPermission) {
                      widget.goNext();
                    } else {
                      showDialog(
                        context: context,
                        builder: (c) => getDialog(
                          context,
                          () {
                            Navigator.of(context).pop();
                            openAppSettings();
                          },
                          () {},
                          'Permissions Required',
                          'This app needs Bluetooth and Location permissions to function properly. Please enable them in the settings.',
                          okButtonText: 'Open Settings',
                          singleButton: true,
                        ),
                        barrierDismissible: false,
                      );
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
            );
          },
        ),
        const SizedBox(
          height: 12,
        ),
        InkWell(
          child: Text(
            'Need Help?',
            style: TextStyle(
              color: Colors.grey.shade300,
              decoration: TextDecoration.underline,
            ),
          ),
          onTap: () {
            IntercomManager.instance.intercom.displayMessenger();
          },
        ),
        const SizedBox(height: 10)
      ],
    );
  }
}
