// DEPRECATED: The Flutter desktop app is deprecated and no longer actively maintained.
// The new native macOS app is located at /desktop/ (Swift/SwiftUI + Rust backend).
// See /desktop/README.md for setup and development instructions.

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/desktop/pages/desktop_home_wrapper.dart';
import 'package:omi/desktop/pages/onboarding/desktop_onboarding_wrapper.dart';
import 'package:omi/pages/persona/persona_profile.dart';
import 'package:omi/providers/auth_provider.dart';

/// @deprecated Use the native Swift macOS app at /desktop/ instead.
class DesktopApp extends StatefulWidget {
  const DesktopApp({super.key});

  @override
  State<DesktopApp> createState() => _DesktopAppState();
}

class _DesktopAppState extends State<DesktopApp> {
  bool _showDeprecationBanner = true;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        if (_showDeprecationBanner)
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            color: const Color(0xFFDC2626),
            child: Row(
              children: [
                const Icon(Icons.warning_amber_rounded, color: Colors.white, size: 20),
                const SizedBox(width: 10),
                Expanded(
                  child: Row(
                    children: [
                      const Text(
                        'This app is deprecated. Please migrate to the ',
                        style: TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w500),
                      ),
                      MouseRegion(
                        cursor: SystemMouseCursors.click,
                        child: GestureDetector(
                          onTap: () => launchUrl(Uri.parse('https://macos.omi.me')),
                          child: const Text(
                            'v2 Desktop app',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 13,
                              fontWeight: FontWeight.w700,
                              decoration: TextDecoration.underline,
                              decorationColor: Colors.white,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                MouseRegion(
                  cursor: SystemMouseCursors.click,
                  child: GestureDetector(
                    onTap: () => setState(() => _showDeprecationBanner = false),
                    child: const Icon(Icons.close, color: Colors.white, size: 18),
                  ),
                ),
              ],
            ),
          ),
        Expanded(
          child: Consumer<AuthenticationProvider>(
            builder: (context, authProvider, child) {
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
          ),
        ),
      ],
    );
  }
}
