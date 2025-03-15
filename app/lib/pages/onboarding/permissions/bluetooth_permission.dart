import 'package:flutter/material.dart';
import 'package:friend_private/providers/onboarding_provider.dart';
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
            InkWell(
              onTap: () async {
                if (!provider.hasBluetoothPermission) {
                  await provider.askForBluetoothPermissions();
                } else {
                  provider.updateBluetoothPermission(false);
                }
              },
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 8.0),
                child: Row(
                  children: [
                    // Custom checkbox that's part of the clickable area
                    Checkbox(
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
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                    ),
                    const SizedBox(width: 8),
                    // Text as part of the clickable area
                    Expanded(
                      child: Text(
                        'Enable Bluetooth access for Friend\'s full experience.',
                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w500),
                      ),
                    ),
                  ],
                ),
              ),
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
