import 'package:flutter/material.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/onboarding/device_selection.dart';
import 'package:omi/pages/persona/persona_profile.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/auth.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:provider/provider.dart';

/// Mobile app tree - wraps existing mobile app functionality
class MobileApp extends StatelessWidget {
  const MobileApp({super.key});

  @override
  Widget build(BuildContext context) {
    // Return the mobile app with existing logic
    return Consumer<AuthenticationProvider>(
      builder: (context, authProvider, child) {
        if (authProvider.isSignedIn()) {
          if (SharedPreferencesUtil().onboardingCompleted) {
            return const HomePageWrapper();
          } else {
            return const OnboardingWrapper();
          }
        } else if (SharedPreferencesUtil().hasOmiDevice == false &&
            SharedPreferencesUtil().hasPersonaCreated &&
            SharedPreferencesUtil().verifiedPersonaId != null) {
          return const PersonaProfilePage();
        } else {
          return const DeviceSelectionPage();
        }
      },
    );
  }
}
