import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/connectivity_service.dart';
import 'package:omi/services/onboarding_sync_service.dart';

abstract final class OnboardingSyncRuntime {
  static const _key = 'onboarding_pending_v1';
  static final service = OnboardingSyncService(
    read: (owner) => SharedPreferencesUtil().getString('$_key:$owner'),
    write: (owner, value) => value.isEmpty
        ? SharedPreferencesUtil().remove('$_key:$owner')
        : SharedPreferencesUtil().saveString('$_key:$owner', value),
    isCurrent: AuthService.instance.isSessionSnapshotCurrent,
    send: (session, fields) => updateUserOnboardingState(
      session: session,
      completed: fields['completed'] as bool?,
      acquisitionSource: fields['acquisition_source'] as String?,
      deviceOnboardingCompleted: fields['device_onboarding_completed'] as bool?,
    ),
  )..setActive(false);
  static StreamSubscription? _auth;
  static StreamSubscription? _generation;
  static StreamSubscription? _connection;

  static void initialize() {
    if (_auth != null) return;
    service.setActive(true);
    // Invalidate immediately, including a same-account sign-out/sign-in (ABA).
    _generation = AuthService.instance.sessionGenerationEvents.listen((_) => service.bindSession(null));
    _auth = FirebaseAuth.instance.authStateChanges().listen((_) => wake());
    _connection = ConnectivityService().onConnectionChange.listen((connected) {
      if (connected) wake();
    });
  }

  static void wake() {
    final session = AuthService.instance.captureSessionSnapshot();
    service.bindSession(session);
    if (session == null) return;
    final pending = service.pending(session.ownerUid);
    // Recover a crash after intent persisted but before navigation/local flags.
    if (pending['completed'] == true) SharedPreferencesUtil().onboardingCompleted = true;
    if (pending['device_onboarding_completed'] == true) SharedPreferencesUtil().deviceOnboardingCompleted = true;
    if (pending['acquisition_source'] is String) {
      SharedPreferencesUtil().foundOmiSource = pending['acquisition_source'] as String;
    }
    unawaited(service.flush());
  }

  static Future<bool> enqueue({bool? completed, String? acquisitionSource, bool? deviceOnboardingCompleted}) async {
    try {
      final session = AuthService.instance.captureSessionSnapshot();
      if (session == null) return false;
      service.bindSession(session);
      return await service.enqueue(
        session,
        completed: completed,
        acquisitionSource: acquisitionSource,
        deviceOnboardingCompleted: deviceOnboardingCompleted,
      );
    } catch (_) {
      return false;
    }
  }

  static bool get hasPendingAcquisitionSource {
    final session = AuthService.instance.captureSessionSnapshot();
    return session != null && service.pending(session.ownerUid).containsKey('acquisition_source');
  }

  static void setActive(bool active) {
    service.setActive(active);
    if (active) wake();
  }

  static Future<void> dispose() async {
    service.dispose();
    await _auth?.cancel();
    await _generation?.cancel();
    await _connection?.cancel();
  }
}
