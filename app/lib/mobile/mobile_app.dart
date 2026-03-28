import 'dart:io';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/onboarding/device_selection.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/pages/persona/persona_profile.dart';
import 'package:omi/providers/auth_provider.dart';

class MobileApp extends StatelessWidget {
  const MobileApp({super.key});

  bool _needsPermissionsOnboarding() {
    final preferences = SharedPreferencesUtil();
    final needsNotifications = !preferences.notificationsEnabled;
    final needsLocation = !preferences.locationEnabled;
    final needsBackground = Platform.isAndroid && !preferences.backgroundPermissionEnabled;

    final missingRequiredPermission = needsNotifications || needsLocation || needsBackground;
    return missingRequiredPermission && !preferences.hasSeenForcedPermissionsOnboarding;
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthenticationProvider>(
      builder: (context, authProvider, child) {
        if (authProvider.isSignedIn()) {
          if (SharedPreferencesUtil().onboardingCompleted) {
            if (_needsPermissionsOnboarding()) {
              return const OnboardingWrapper(forcePermissionsStep: true);
            }
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
