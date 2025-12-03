import 'package:flutter/material.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/onboarding/device_selection.dart';
import 'package:omi/pages/persona/persona_profile.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:provider/provider.dart';
import 'package:omi/env/env.dart';

class MobileApp extends StatelessWidget {
  const MobileApp({super.key});

  // Dev bypass for local testing
  bool get _isDevBypass {
    final apiUrl = Env.apiBaseUrl ?? '';
    return apiUrl.contains('10.0.2.2') || apiUrl.contains('localhost') || apiUrl.contains('192.168.');
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthenticationProvider>(
      builder: (context, authProvider, child) {
        if (_isDevBypass || authProvider.isSignedIn()) {
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
