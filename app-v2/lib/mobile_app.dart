import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/l10n/gen/app_localizations.dart';
import 'package:nooto_v2/onboarding/onboarding_chat_provider.dart';
import 'package:nooto_v2/onboarding/onboarding_chat_screen.dart';
import 'package:nooto_v2/onboarding/welcome_screen.dart';
import 'package:nooto_v2/providers/auth_provider.dart';
import 'package:nooto_v2/providers/locale_provider.dart';
import 'package:nooto_v2/shell/shell_screen.dart';
import 'package:nooto_v2/theme/app_theme.dart';

class MobileApp extends StatelessWidget {
  const MobileApp({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<LocaleProvider>(
      builder: (context, locale, _) => MaterialApp(
        title: 'Nooto',
        debugShowCheckedModeBanner: false,
        theme: buildAppTheme(),
        locale: locale.locale,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: const _Router(),
      ),
    );
  }
}

class _Router extends StatelessWidget {
  const _Router();

  @override
  Widget build(BuildContext context) {
    return Consumer2<AuthChangeProvider, OnboardingChatProvider>(
      builder: (context, auth, chat, _) {
        if (!auth.isSignedIn) return const WelcomeScreen();
        if (!chat.completed) return const OnboardingChatScreen();
        return const ShellScreen();
      },
    );
  }
}
