import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:intercom_flutter/intercom_flutter.dart';
import 'package:provider/provider.dart';

class PermissionsDesktopWidget extends StatefulWidget {
  final VoidCallback goNext;

  const PermissionsDesktopWidget({super.key, required this.goNext});

  @override
  State<PermissionsDesktopWidget> createState() => _PermissionsDesktopWidgetState();
}

class _PermissionsDesktopWidgetState extends State<PermissionsDesktopWidget> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      // Refresh permissions when user returns to the app
      final provider = Provider.of<OnboardingProvider>(context, listen: false);
      provider.updatePermissions();
    }
  }

  void _showPermissionDialog({
    required String title,
    required String description,
    required VoidCallback onContinue,
  }) {
    showCupertinoDialog(
      context: context,
      builder: (ctx) {
        return CupertinoAlertDialog(
          title: Text(
            title,
            style: const TextStyle(
              fontSize: 17,
              fontWeight: FontWeight.w600,
              color: Colors.white,
            ),
          ),
          content: Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              description,
              style: const TextStyle(
                fontSize: 13,
                color: Colors.white,
                height: 1.4,
              ),
            ),
          ),
          actions: [
            CupertinoDialogAction(
              child: Text(
                'Cancel',
                style: TextStyle(
                  color: Colors.grey.shade500,
                  fontSize: 17,
                ),
              ),
              onPressed: () => Navigator.of(context).pop(),
            ),
            CupertinoDialogAction(
              isDefaultAction: true,
              child: const Text(
                'Continue',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 17,
                ),
              ),
              onPressed: () {
                Navigator.of(context).pop();
                onContinue();
              },
            ),
          ],
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<OnboardingProvider>(builder: (context, provider, child) {
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            // Informational header section
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              margin: const EdgeInsets.only(bottom: 16),
              decoration: BoxDecoration(
                color: Color(0xFF35343B).withOpacity(0.3),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: const Color.fromARGB(255, 188, 99, 121).withOpacity(0.3),
                  width: 1,
                ),
              ),
              child: Row(
                children: [
                  const Icon(
                    Icons.info_outline,
                    color: Color.fromARGB(255, 188, 99, 121),
                    size: 16,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Select permissions to grant - we\'ll guide you through each one',
                      style: TextStyle(
                        fontSize: 12,
                        color: Colors.grey.shade300,
                        height: 1.2,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            CheckboxListTile(
              value: provider.hasBluetoothPermission,
              onChanged: (s) async {
                if (s != null) {
                  if (s) {
                    _showPermissionDialog(
                      title: 'Bluetooth Access',
                      description: 'This app uses Bluetooth to connect and communicate with your device. Your device data stays private and secure.',
                      onContinue: () async {
                        await provider.askForBluetoothPermissions();
                      },
                    );
                  } else {
                    provider.updateBluetoothPermission(false);
                  }
                }
              },
              title: const Text(
                'Connect to your Omi device via Bluetooth',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w500),
              ),
              contentPadding: const EdgeInsets.only(left: 8),
              checkboxShape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            ),
            CheckboxListTile(
              value: provider.hasLocationPermission,
              onChanged: (s) async {
                if (s != null) {
                  if (s) {
                    _showPermissionDialog(
                      title: 'Location Services',
                      description: 'This app may use your location to tag your conversations and improve your experience.',
                      onContinue: () async {
                        await provider.askForLocationPermissions();
                      },
                    );
                  } else {
                    provider.updateLocationPermission(false);
                  }
                }
              },
              title: const Text(
                'Access location to improve your experience',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w500),
              ),
              contentPadding: const EdgeInsets.only(left: 8),
              checkboxShape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            ),
            CheckboxListTile(
              value: provider.hasNotificationPermission,
              onChanged: (s) async {
                if (s != null) {
                  if (s) {
                    _showPermissionDialog(
                      title: 'Notifications',
                      description: 'This app would like to send you notifications to keep you informed about important updates and activities. If permission is denied, we\'ll redirect you to System Preferences.',
                      onContinue: () async {
                        await provider.askForNotificationPermissions();
                      },
                    );
                  } else {
                    provider.updateNotificationPermission(false);
                  }
                }
              },
              title: const Text(
                'Receive Important Notifications',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w500),
              ),
              contentPadding: const EdgeInsets.only(left: 8),
              checkboxShape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            ),
            const SizedBox(height: 16),
            provider.isLoading
                ? const CircularProgressIndicator(
                    color: Colors.white,
                  )
                : Row(
                    children: [
                      Expanded(
                        child: Container(
                          width: double.infinity,
                          decoration: BoxDecoration(
                            border: const GradientBoxBorder(
                              gradient: LinearGradient(colors: [Color.fromARGB(127, 208, 208, 208), Color.fromARGB(127, 188, 99, 121), Color.fromARGB(127, 86, 101, 182), Color.fromARGB(127, 126, 190, 236)]),
                              width: 2,
                            ),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: MaterialButton(
                            padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
                            onPressed: () async {
                              provider.setLoading(false);
                              widget.goNext();
                            },
                            child: Text(
                              (provider.hasBluetoothPermission || provider.hasLocationPermission || provider.hasNotificationPermission) ? 'Continue' : 'Skip',
                              style: const TextStyle(
                                decoration: TextDecoration.none,
                              ),
                            ),
                          ),
                        ),
                      )
                    ],
                  ),
            const SizedBox(
              height: 12,
            ),
            PlatformService.isIntercomSupported
                ? InkWell(
                    child: Text(
                      'Need Help?',
                      style: TextStyle(
                        color: Colors.grey.shade300,
                        decoration: TextDecoration.underline,
                      ),
                    ),
                    onTap: () {
                      Intercom.instance.displayMessenger();
                    },
                  )
                : const SizedBox.shrink(),
          ],
        ),
      );
    });
  }
}
