import 'package:flutter/material.dart';
import 'package:friend_private/services/notification_service.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';

class PermissionsPage extends StatefulWidget {
  final VoidCallback goNext;

  const PermissionsPage({super.key, required this.goNext});

  @override
  State<PermissionsPage> createState() => _PermissionsPageState();
}

class _PermissionsPageState extends State<PermissionsPage> {
  bool switchValue = false;

  @override
  Widget build(BuildContext context) {
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
            value: switchValue,
            onChanged: (s) {
              setState(() {
                switchValue = s!;
              });
              NotificationService.instance.requestNotificationPermissions();
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
                  decoration: switchValue
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
                      switchValue ? 'Continue' : 'Skip',
                      style: TextStyle(
                        decoration: switchValue ? TextDecoration.none : TextDecoration.underline,
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
  }
}
