// Every registered visual audit scenario for current main. Add a scenario to the file for its area
// under scenarios/, and a new area's list here. Ids are unique; the smoke test enforces it.
import 'package:omi/ui/ui.dart';

import 'fakes.dart';
import 'harness.dart';
import 'scenarios/apps.dart';
import 'scenarios/capture.dart';
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

final auditSuite = AuditSuite(
  name: 'current',
  providers: defaultAuditProviders,
  theme: buildOmiTheme,
  scenarios: [
    ...settingsScenarios,
    ...settingsPagesScenarios,
    ...homeScenarios,
    ...captureScenarios,
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
