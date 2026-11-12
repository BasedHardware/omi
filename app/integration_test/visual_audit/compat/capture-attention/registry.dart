// The suite as it was before the capture-attention change (UNTIL): every area
// current main audits, at its then-current shape, with only the capture area
// swapped for the pre-change registry (the current capture scenarios reference
// ActivityPage's capture attention rows, which did not exist at these
// revisions; the other areas' scenarios compile unchanged at both revisions).
// See ../README.md.
import 'package:omi/ui/ui.dart';

import '../../fakes.dart';
import '../../harness.dart';
import 'scenarios/apps.dart';
import 'scenarios/auth.dart';
import 'scenarios/capture.dart';
import 'scenarios/chat_apps.dart';
import 'scenarios/chat.dart';
import 'scenarios/conversation_detail.dart';
import 'scenarios/conversations.dart';
import 'scenarios/device.dart';
import 'scenarios/home.dart';
import 'scenarios/imports.dart';
import 'scenarios/memories.dart';
import 'scenarios/offline_processing.dart';
import 'scenarios/onboarding.dart';
import 'scenarios/review.dart';
import 'scenarios/search.dart';
import 'scenarios/settings.dart';
import 'scenarios/settings_pages.dart';
import 'scenarios/speaker_labels.dart';
import 'scenarios/tasks.dart';

final auditSuite = AuditSuite(
  name: 'pre-capture-attention',
  providers: defaultAuditProviders,
  theme: buildOmiTheme,
  scenarios: [
    ...settingsScenarios,
    ...settingsPagesScenarios,
    ...importsScenarios,
    ...homeScenarios,
    ...captureScenarios,
    ...deviceScenarios,
    ...conversationsScenarios,
    ...offlineProcessingScenarios,
    ...speakerLabelScenarios,
    ...reviewScenarios,
    ...conversationDetailScenarios,
    ...memoriesScenarios,
    ...tasksScenarios,
    ...chatScenarios,
    ...searchScenarios,
    ...appsScenarios,
    ...chatAppsScenarios,
    ...onboardingScenarios,
    ...authScenarios,
  ],
);
