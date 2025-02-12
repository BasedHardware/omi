import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/onboarding/wrapper.dart';
import 'package:friend_private/pages/onboarding/no_device_wrapper.dart';

class DeviceSelectionPage extends StatelessWidget {
  const DeviceSelectionPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Text(
                'Do you have an Omi device?',
                style: TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 40),
              _buildOptionButton(
                context,
                'Yes, I have an Omi device',
                'Continue with device setup',
                () {
                  SharedPreferencesUtil().hasOmiDevice = true;
                  // Route to existing onboarding flow with sign in
                  Navigator.pushReplacement(
                    context,
                    MaterialPageRoute(builder: (context) => const OnboardingWrapper()),
                  );
                },
              ),
              const SizedBox(height: 20),
              _buildOptionButton(
                context,
                'No, I don\'t have a device',
                'Continue without device',
                () {
                  SharedPreferencesUtil().hasOmiDevice = false;
                  // Route to new no-device flow
                  Navigator.pushReplacement(
                    context,
                    MaterialPageRoute(builder: (context) => const NoDeviceOnboardingWrapper()),
                  );
                },
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildOptionButton(
    BuildContext context,
    String title,
    String subtitle,
    VoidCallback onTap,
  ) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          border: Border.all(color: Colors.white.withOpacity(0.2)),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: const TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w600,
                color: Colors.white,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              subtitle,
              style: TextStyle(
                fontSize: 14,
                color: Colors.white.withOpacity(0.7),
              ),
            ),
          ],
        ),
      ),
    );
  }
} 