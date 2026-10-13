import 'package:permission_handler/permission_handler.dart';

import 'package:omi/utils/analytics/registry/events.g.dart';

/// One emission per permission per distinct decision (granted / permanently denied).
class OnboardingPermissionDecisionLog {
  final Set<String> _seen = {};

  bool claim({
    required OnboardingPermissionResultPermission permission,
    required bool granted,
    required bool permanentlyDenied,
    bool servicesDisabled = false,
  }) {
    return _seen.add('${permission.wireName}|$granted|$permanentlyDenied|$servicesDisabled');
  }
}

bool permissionStatusIsPermanentDenial(PermissionStatus status) =>
    status == PermissionStatus.permanentlyDenied || status == PermissionStatus.restricted;

OnboardingPermissionResultPermission? onboardingPermissionWireName(String name) {
  return switch (name) {
    'notifications' => OnboardingPermissionResultPermission.notifications,
    'location' => OnboardingPermissionResultPermission.location,
    'background' || 'background_activity' => OnboardingPermissionResultPermission.backgroundActivity,
    _ => null,
  };
}
