import 'package:flutter/material.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/onboarding/device_selection.dart';
import 'package:omi/pages/persona/persona_profile.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:provider/provider.dart';

class MobileApp extends StatelessWidget {
  const MobileApp({super.key});

  @override
  Widget build(BuildContext context) {
    final isWebhookOnlyMode = SharedPreferencesUtil().webhookOnlyModeEnabled;
    final hasUid = SharedPreferencesUtil().uid.isNotEmpty;
    final onboardingDone = SharedPreferencesUtil().onboardingCompleted;

    debugPrint('📱 MobileApp routing: webhookOnly=$isWebhookOnlyMode, hasUid=$hasUid, onboardingDone=$onboardingDone');

    // FORCE bypass auth if webhook-only mode
    if (isWebhookOnlyMode && hasUid) {
      debugPrint('📱 BYPASSING AUTH - Going to HomePageWrapper');
      return const HomePageWrapper();
    }

    return Consumer<AuthenticationProvider>(
      builder: (context, authProvider, child) {
        final isWebhookOnlyModeInner = SharedPreferencesUtil().webhookOnlyModeEnabled;
        final hasAnonymousUid = SharedPreferencesUtil().uid.isNotEmpty;

        if (authProvider.isSignedIn() || (isWebhookOnlyModeInner && hasAnonymousUid)) {
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
