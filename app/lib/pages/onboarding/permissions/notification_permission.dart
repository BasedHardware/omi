import 'package:flutter/material.dart';
import 'package:friend_private/providers/onboarding_provider.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:provider/provider.dart';

class NotificationPermissionWidget extends StatefulWidget {
  final VoidCallback goNext;

  const NotificationPermissionWidget({super.key, required this.goNext});

  @override
  State<NotificationPermissionWidget> createState() => _NotificationPermissionWidgetState();
}

class _NotificationPermissionWidgetState extends State<NotificationPermissionWidget> {
  @override
  Widget build(BuildContext context) {
    return Consumer<OnboardingProvider>(builder: (context, provider, child) {
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            CheckboxListTile(
              value: provider.hasNotificationPermission,
              onChanged: (s) async {
                if (s != null) {
                  if (s) {
                    await provider.askForNotificationPermissions();
                  } else {
                    provider.updateNotificationPermission(false);
                  }
                }
              },
              title: const Text(
                'Enable notification access for Friend\'s full experience.',
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
                    child: MaterialButton(
                      padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
                      onPressed: () {
                        if (provider.hasNotificationPermission) {
                          widget.goNext();
                        } else {
                          showDialog(
                            context: context,
                            builder: (c) => getDialog(
                              context,
                              () {
                                Navigator.of(context).pop();
                              },
                              () {
                                Navigator.of(context).pop();
                              },
                              'Allow Notifications',
                              'This app needs notification permissions to improve your experience.',
                              singleButton: true,
                            ),
                          );
                        }
                      },
                      child: const Text(
                        'Continue',
                        style: TextStyle(
                          decoration: TextDecoration.none,
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
