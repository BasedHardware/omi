import 'package:flutter_test/flutter_test.dart';
import 'package:omi/pages/onboarding/permissions/onboarding_permission_decision.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:permission_handler/permission_handler.dart';

void main() {
  test('a permission decision is recorded once per granted and permanent-denial pair', () {
    final log = OnboardingPermissionDecisionLog();
    expect(
      log.claim(
        permission: OnboardingPermissionResultPermission.notifications,
        granted: true,
        permanentlyDenied: false,
      ),
      isTrue,
    );
    expect(
      log.claim(
        permission: OnboardingPermissionResultPermission.notifications,
        granted: true,
        permanentlyDenied: false,
      ),
      isFalse,
    );
    expect(
      log.claim(
        permission: OnboardingPermissionResultPermission.notifications,
        granted: false,
        permanentlyDenied: true,
      ),
      isTrue,
    );
    expect(
      log.claim(
        permission: OnboardingPermissionResultPermission.location,
        granted: false,
        permanentlyDenied: true,
      ),
      isTrue,
    );
    expect(
      log.claim(
        permission: OnboardingPermissionResultPermission.location,
        granted: false,
        permanentlyDenied: false,
        servicesDisabled: true,
      ),
      isTrue,
    );
    expect(
      log.claim(
        permission: OnboardingPermissionResultPermission.location,
        granted: false,
        permanentlyDenied: false,
      ),
      isTrue,
    );
  });

  test('permanent denial is restricted or permanentlyDenied', () {
    expect(permissionStatusIsPermanentDenial(PermissionStatus.permanentlyDenied), isTrue);
    expect(permissionStatusIsPermanentDenial(PermissionStatus.restricted), isTrue);
    expect(permissionStatusIsPermanentDenial(PermissionStatus.denied), isFalse);
    expect(permissionStatusIsPermanentDenial(PermissionStatus.granted), isFalse);
  });

  test('permission names stay the closed onboarding set', () {
    expect(onboardingPermissionWireName('notifications'), OnboardingPermissionResultPermission.notifications);
    expect(onboardingPermissionWireName('location'), OnboardingPermissionResultPermission.location);
    expect(
        onboardingPermissionWireName('background_activity'), OnboardingPermissionResultPermission.backgroundActivity);
    expect(onboardingPermissionWireName('bluetooth'), isNull);
  });
}
