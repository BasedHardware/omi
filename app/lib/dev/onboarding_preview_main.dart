// Dev-only entry point for iterating on onboarding UI/animations without a
// full app build (no Firebase, no backend, no device pairing).
//
// Run:  flutter run -d chrome -t lib/dev/onboarding_preview_main.dart
//
// Walks the full flow in order: Get Started -> Sign in -> Data privacy ->
// Name -> Language -> How did you find us -> Permissions -> Find a quiet
// place -> Answer with voice -> What we know -> You're all set.
//
// The splash step is the real production widget (it needs no
// backend/Firebase to render — pulling in almost any other real onboarding
// widget drags in SharedPreferencesUtil, which transitively imports the
// Bluetooth/transcription stack and fails to compile for web via
// whisper_flutter_new's dart:ffi dependency). Every other step below is a
// visual stand-in that mirrors the real screen's copy and layout — see
// lib/dev/preview_steps.dart. All steps share the same
// OnboardingPageTransition used by the real onboarding wrapper, so the
// between/during-page motion you see here matches production.
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'package:omi/dev/preview_steps.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/splash/splash_page.dart';
import 'package:omi/widgets/onboarding_page_transition.dart';

void main() {
  runApp(const OnboardingPreviewApp());
}

class OnboardingPreviewApp extends StatelessWidget {
  const OnboardingPreviewApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark(),
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: const _OnboardingPreviewFlow(),
    );
  }
}

class _OnboardingPreviewFlow extends StatefulWidget {
  const _OnboardingPreviewFlow();

  @override
  State<_OnboardingPreviewFlow> createState() => _OnboardingPreviewFlowState();
}

class _OnboardingPreviewFlowState extends State<_OnboardingPreviewFlow> {
  static const int kSplash = 0;
  static const int kSignIn = 1;
  static const int kConsent = 2;
  static const int kName = 3;
  static const int kLanguage = 4;
  static const int kFoundUs = 5;
  static const int kPermissions = 6;
  static const int kQuietPlace = 7;
  static const int kVoice = 8;
  static const int kKnowledgeGraph = 9;
  static const int kComplete = 10;
  static const int kLast = kComplete;

  int _index = kSplash;

  void _goNext() {
    if (_index < kLast) setState(() => _index += 1);
  }

  void _goBack() {
    if (_index > kSplash) setState(() => _index -= 1);
  }

  void _restart() => setState(() => _index = kSplash);

  Widget _buildStep(int index) {
    switch (index) {
      case kSplash:
        return OnboardingSplashPage(goNext: _goNext);
      case kSignIn:
        return PreviewSignInStep(goNext: _goNext);
      case kConsent:
        return PreviewConsentStep(goNext: _goNext);
      case kName:
        return PreviewNameStep(goNext: _goNext);
      case kLanguage:
        return PreviewLanguageStep(goNext: _goNext);
      case kFoundUs:
        return PreviewFoundUsStep(goNext: _goNext);
      case kPermissions:
        return PreviewPermissionsStep(goNext: _goNext);
      case kQuietPlace:
        return PreviewQuietPlaceStep(goNext: _goNext);
      case kVoice:
        return PreviewVoiceStep(goNext: _goNext);
      case kKnowledgeGraph:
        return PreviewKnowledgeGraphStep(goNext: _goNext);
      case kComplete:
        return PreviewCompleteStep(onComplete: _restart);
      default:
        return const SizedBox.shrink();
    }
  }

  @override
  Widget build(BuildContext context) {
    final showChrome = _index != kSplash && _index != kComplete;
    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        children: [
          OnboardingPageTransition(pageKey: _index, child: _buildStep(_index)),
          if (showChrome)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 56, 16, 0),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: List.generate(kComplete - kSignIn, (i) {
                  final stepIndex = i + kSignIn;
                  final active = stepIndex == _index;
                  return Container(
                    margin: const EdgeInsets.symmetric(horizontal: 4),
                    width: active ? 12 : 8,
                    height: active ? 12 : 8,
                    decoration: BoxDecoration(
                      color: stepIndex <= _index ? Colors.white : Colors.grey.shade700,
                      shape: BoxShape.circle,
                    ),
                  );
                }),
              ),
            ),
          if (_index > kSplash && _index != kComplete)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 40, 0, 0),
              child: Align(
                alignment: Alignment.topLeft,
                child: IconButton(
                  onPressed: _goBack,
                  icon: const Icon(Icons.arrow_back, color: Colors.white),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
