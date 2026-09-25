// The equivalent pages at revisions before the Omi UI program (#17297, the first commit in UNTIL):
// the old Settings sheet and Profile page, the pre-primitives conversation, memories, tasks, chat,
// apps, device, onboarding and home screens. Ids match the current suite where a page has an
// equivalent; pages that did not exist yet are left out. See ../README.md.
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import '../../harness.dart';
import 'fakes.dart';
import 'scenarios/apps.dart';
import 'scenarios/chat.dart';
import 'scenarios/conversation_detail.dart';
import 'scenarios/conversations.dart';
import 'scenarios/device.dart';
import 'scenarios/home.dart';
import 'scenarios/memories.dart';
import 'scenarios/onboarding.dart';
import 'scenarios/settings.dart';
import 'scenarios/settings_pages.dart';
import 'scenarios/tasks.dart';

/// The theme lib/main.dart passed to MaterialApp at these revisions.
ThemeData preUiProgramTheme() => ThemeData(
      useMaterial3: false,
      colorScheme: const ColorScheme.dark(
        primary: Colors.black,
        secondary: Color(0xFF35343B),
        surface: Colors.black38,
      ),
      snackBarTheme: const SnackBarThemeData(
        backgroundColor: Color(0xFF1F1F25),
        contentTextStyle: TextStyle(fontSize: 16, color: Colors.white, fontWeight: FontWeight.w500),
      ),
      textTheme: TextTheme(
        titleLarge: const TextStyle(fontSize: 18, color: Colors.white),
        titleMedium: const TextStyle(fontSize: 16, color: Colors.white),
        bodyMedium: const TextStyle(fontSize: 14, color: Colors.white),
        labelMedium: TextStyle(fontSize: 12, color: Colors.grey.shade200),
      ),
      textSelectionTheme: const TextSelectionThemeData(
        cursorColor: Colors.white,
        selectionColor: Colors.white24,
        selectionHandleColor: Colors.white,
      ),
      cupertinoOverrideTheme: const CupertinoThemeData(primaryColor: Colors.white),
    );

final auditSuite = AuditSuite(
  name: 'pre-ui-program',
  providers: defaultAuditProviders,
  theme: preUiProgramTheme,
  // The theme left the scaffold at Material's default grey; HomePage painted its tabs on
  // colorScheme.primary (black), which is what a user saw behind these pages.
  hostBackground: Colors.black,
  scenarios: [
    ...settingsScenarios,
    ...settingsPagesScenarios,
    ...homeScenarios,
    ...deviceScenarios,
    ...conversationsScenarios,
    ...conversationDetailScenarios,
    ...memoriesScenarios,
    ...tasksScenarios,
    ...chatScenarios,
    ...appsScenarios,
    ...onboardingScenarios,
  ],
);
