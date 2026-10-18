// The capture scenarios as they were before the capture-attention change (UNTIL): the recovery
// banner on the capturing page under its current id, and the live outage scene. The current suite
// does not compile at these revisions — its capture scenarios reference ActivityPage's capture
// attention rows — so this suite carries the capture area alone; the other areas' scenarios are
// unchanged between the two revisions and this suite exists to serve the stacked before/after
// capture. See ../README.md.
import 'package:omi/ui/ui.dart';

import '../../fakes.dart';
import '../../harness.dart';
import 'scenarios/capture.dart';

final auditSuite = AuditSuite(
  name: 'pre-capture-attention',
  providers: defaultAuditProviders,
  theme: buildOmiTheme,
  scenarios: captureScenarios,
);
