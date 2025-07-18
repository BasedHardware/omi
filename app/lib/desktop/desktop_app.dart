import 'package:flutter/material.dart';
import 'package:omi/desktop/pages/onboarding/desktop_onboarding_wrapper.dart';
import 'package:omi/desktop/pages/desktop_home_wrapper.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/persona/persona_profile.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:provider/provider.dart';

class DesktopApp extends StatelessWidget {
  const DesktopApp({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthenticationProvider>(
      builder: (context, authProvider, child) {
        if (authProvider.isSignedIn()) {
          if (SharedPreferencesUtil().onboardingCompleted) {
            return const DesktopHomePageWrapper();
          } else {
            return const DesktopOnboardingWrapper();
          }
        } else if (SharedPreferencesUtil().hasOmiDevice == false &&
            SharedPreferencesUtil().hasPersonaCreated &&
            SharedPreferencesUtil().verifiedPersonaId != null) {
          return const PersonaProfilePage();
        } else {
          return const DesktopOnboardingWrapper();
        }
      },
    );
  }
}
