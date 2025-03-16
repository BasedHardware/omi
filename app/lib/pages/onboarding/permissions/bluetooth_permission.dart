import 'package:flutter/material.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';

class BluetoothPermissionWidget extends StatefulWidget {
  final VoidCallback goNext;

  const BluetoothPermissionWidget({super.key, required this.goNext});

  @override
  State<BluetoothPermissionWidget> createState() => _BluetoothPermissionWidgetState();
}

class _BluetoothPermissionWidgetState extends State<BluetoothPermissionWidget> {
  @override
  Widget build(BuildContext context) {
    return Consumer<OnboardingProvider>(builder: (context, provider, child) {
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            // Text(
            //   'For a personalized experience, we need permissions to send you notifications and read your location information.',
            //   style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
            //   textAlign: TextAlign.center,
            // ),
            // const SizedBox(height: 80),
            CheckboxListTile(
              value: provider.hasBluetoothPermission,
              onChanged: (s) async {
                print('s: $s');
                if (s != null) {
                  if (s) {
                    await provider.askForBluetoothPermissions();
                  } else {
                    provider.updateBluetoothPermission(false);
                  }
                }
              },
              title: const Text(
                'Enable Bluetooth access for Omi\'s full experience.',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w500),
              ),
              contentPadding: const EdgeInsets.only(left: 8),
              // controlAffinity: ListTileControlAffinity.leading,
              checkboxShape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: Container(
                    width: double.infinity,
                    decoration: provider.hasBluetoothPermission
                        ? BoxDecoration(
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
                          )
                        : null,
                    child: MaterialButton(
                      padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
                      onPressed: () {
                        if (!provider.hasBluetoothPermission) {
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
                      child: Text(
                        provider.hasBluetoothPermission ? 'Continue' : 'Skip',
                        style: TextStyle(
                          decoration: provider.hasBluetoothPermission ? TextDecoration.none : TextDecoration.underline,
                        ),
                      ),
                    ),
                  ),
                )
              ],
            ),
          ],
        ),
      );
    });
  }
}
