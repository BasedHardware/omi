import 'package:flutter/material.dart';
import 'package:friend_private/providers/onboarding_provider.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:provider/provider.dart';

class BackgroundPermissionWidget extends StatefulWidget {
  final VoidCallback goNext;

  const BackgroundPermissionWidget({super.key, required this.goNext});

  @override
  State<BackgroundPermissionWidget> createState() => _BackgroundPermissionWIdgetState();
}

class _BackgroundPermissionWIdgetState extends State<BackgroundPermissionWidget> {
  @override
  Widget build(BuildContext context) {
    return Consumer<OnboardingProvider>(
      builder: (context, provider, child) {
        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              CheckboxListTile(
                value: provider.hasBackgroundPermission,
                onChanged: (s) async {
                  if (s != null) {
                    if (s) {
                      await provider.askForBackgroundPermissions();
                    } else {
                      provider.updateBackgroundPermission(false);
                    }
                  }
                },
                title: const Text(
                  'Allow Omi to run in the background to improve your experience',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w500),
                ),
                contentPadding: const EdgeInsets.only(left: 8),
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
                          if (provider.hasBackgroundPermission) {
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
                                'Allow Background Access',
                                'This app needs background permissions to be able to function properly when minimized.',
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
      },
    );
  }
}
