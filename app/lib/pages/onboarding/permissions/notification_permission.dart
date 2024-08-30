import 'package:flutter/material.dart';
import 'package:friend_private/providers/onboarding_provider.dart';
import 'package:friend_private/services/notification_service.dart';
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
            // Text(
            //   'For a personalized experience, we need permissions to send you notifications and read your location information.',
            //   style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
            //   textAlign: TextAlign.center,
            // ),
            // const SizedBox(height: 80),
            CheckboxListTile(
              value: provider.hasNotificationPermission,
              onChanged: (s) async {
                print('s: $s');
                if (s != null) {
                  if (s) {
                    await provider.askForNotificationPermissions();
                  } else {
                    provider.updateNotificationPermission(false);
                  }
                  var isAllowed = await NotificationService.instance.hasNotificationPermissions();
                  provider.updateNotificationPermission(isAllowed);
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
                    decoration: provider.hasNotificationPermission
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
                        // TODO: if toggle not on, show ignore
                        widget.goNext();
                      },
                      child: Text(
                        provider.hasNotificationPermission ? 'Continue' : 'Skip',
                        style: TextStyle(
                          decoration:
                              provider.hasNotificationPermission ? TextDecoration.none : TextDecoration.underline,
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
