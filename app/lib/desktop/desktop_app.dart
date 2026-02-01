import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/desktop/pages/desktop_home_wrapper.dart';
import 'package:omi/desktop/pages/onboarding/desktop_onboarding_wrapper.dart';
import 'package:omi/pages/persona/persona_profile.dart';
import 'package:omi/providers/auth_provider.dart';

class DesktopApp extends StatelessWidget {
  const DesktopApp({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthenticationProvider>(
      builder: (context, authProvider, child) {
        // DEBUG: Log routing decision
        final isSignedIn = authProvider.isSignedIn();
        final onboardingCompleted = SharedPreferencesUtil().onboardingCompleted;
        final currentUser = FirebaseAuth.instance.currentUser;
        print('DEBUG DesktopApp: isSignedIn=$isSignedIn, onboardingCompleted=$onboardingCompleted');
        print('DEBUG DesktopApp: currentUser=${currentUser?.uid}, isAnonymous=${currentUser?.isAnonymous}');

        if (isSignedIn) {
          if (onboardingCompleted) {
            print('DEBUG DesktopApp: -> DesktopHomePageWrapper');
            return const DesktopHomePageWrapper();
          } else {
            print('DEBUG DesktopApp: -> DesktopOnboardingWrapper (not completed)');
            return const DesktopOnboardingWrapper();
          }
        } else if (SharedPreferencesUtil().hasOmiDevice == false &&
            SharedPreferencesUtil().hasPersonaCreated &&
            SharedPreferencesUtil().verifiedPersonaId != null) {
          print('DEBUG DesktopApp: -> PersonaProfilePage');
          return const PersonaProfilePage();
        } else {
          print('DEBUG DesktopApp: -> DesktopOnboardingWrapper (not signed in)');
          return const DesktopOnboardingWrapper();
        }
      },
    );
  }
}
