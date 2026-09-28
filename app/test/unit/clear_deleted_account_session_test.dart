import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/auth/clear_deleted_account_session.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('native Siri sign-out fence is durable before Firebase sign-out', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    final order = <String>[];
    final pending = Completer<void>();
    final gateway = _DeletionGateway(Completer<RefreshedAuthToken?>(), onSignOut: () => order.add('firebase'));
    final service = AuthService.forTesting(
      tokenGateway: gateway,
      prepareSiriSignOut: () async {
        order.add('siri-pending');
        await pending.future;
      },
    );

    final signOut = service.signOut();
    await Future<void>.delayed(Duration.zero);
    expect(order, ['siri-pending']);
    pending.complete();
    await signOut;
    expect(order, ['siri-pending', 'firebase']);
  });

  test('account deletion and forced expiry fence Siri before Firebase sign-out', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    for (final reason in [AuthSessionExpirationReason.accountDeleted, AuthSessionExpirationReason.missingToken]) {
      final order = <String>[];
      final gateway = _DeletionGateway(Completer<RefreshedAuthToken?>(), onSignOut: () => order.add('firebase'));
      final service = AuthService.forTesting(
        tokenGateway: gateway,
        prepareSiriSignOut: () async => order.add('siri-pending'),
      );
      await service.expireSession(AuthSessionExpiredEvent(reason: reason));
      expect(order, ['siri-pending', 'firebase'], reason: '$reason');
    }
  });

  test('provider account switch fences Siri before Firebase sign-out', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    final order = <String>[];
    final gateway = _DeletionGateway(Completer<RefreshedAuthToken?>(), onSignOut: () => order.add('firebase'));
    final service = AuthService.forTesting(
      tokenGateway: gateway,
      prepareSiriSignOut: () async => order.add('siri-pending'),
    );
    await service.signOutForAccountSwitch();
    expect(order, ['siri-pending', 'firebase']);
  });

  test('account deletion invalidates late refresh and clears provider state before storage', () async {
    SharedPreferences.setMockInitialValues({'uid': 'user-1', 'authToken': 'old-token'});
    await SharedPreferencesUtil.init();
    final pendingRefresh = Completer<RefreshedAuthToken?>();
    final gateway = _DeletionGateway(pendingRefresh);
    final service = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});
    final order = <String>[];

    final refresh = service.refreshIdToken();
    await clearDeletedAccountSession(
      authService: service,
      clearUserState: () => order.add('providers'),
      clearWal: () async => order.add('wal'),
      clearPreferences: () async {
        order.add('preferences');
        await SharedPreferencesUtil().clear();
      },
    );
    pendingRefresh.complete(RefreshedAuthToken(token: 'late-token', expirationTime: DateTime.now()));

    expect(await refresh, isA<AuthTokenMissingUser>());
    expect(order, ['providers', 'wal', 'preferences']);
    expect(gateway.signOutCalls, 1);
    expect(SharedPreferencesUtil().uid, isEmpty);
    expect(SharedPreferencesUtil().authToken, isEmpty);
    expect(await service.refreshIdToken(), isA<AuthTokenMissingUser>());
    expect(gateway.refreshCalls, 1, reason: 'the deleted Firebase user must not start another refresh');
  });

  test('account deletion clears WAL and preferences when Firebase sign-out fails', () async {
    SharedPreferences.setMockInitialValues({'uid': 'user-1', 'authToken': 'old-token'});
    await SharedPreferencesUtil.init();
    final gateway = _DeletionGateway(Completer<RefreshedAuthToken?>(), failSignOut: true);
    final service = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});
    final order = <String>[];

    await clearDeletedAccountSession(
      authService: service,
      clearUserState: () => order.add('providers'),
      clearWal: () async {
        order.add('wal');
        throw StateError('disk unavailable');
      },
      clearPreferences: () async {
        order.add('preferences');
        await SharedPreferencesUtil().clear();
      },
    );

    expect(order, ['providers', 'wal', 'preferences']);
    expect(gateway.signOutCalls, 1);
    expect(SharedPreferencesUtil().uid, isEmpty);
    expect(SharedPreferencesUtil().authToken, isEmpty);
    expect(await service.refreshIdToken(), isA<AuthTokenMissingUser>());
    expect(gateway.refreshCalls, 0, reason: 'failed platform sign-out must still leave the old user locally terminal');
  });
}

final class _DeletionGateway implements AuthTokenGateway {
  _DeletionGateway(this.pendingRefresh, {this.failSignOut = false, this.onSignOut});

  final Completer<RefreshedAuthToken?> pendingRefresh;
  final bool failSignOut;
  final void Function()? onSignOut;
  int signOutCalls = 0;
  int refreshCalls = 0;

  @override
  AuthUserSnapshot? get currentUser => const AuthUserSnapshot(uid: 'user-1');

  @override
  Future<RefreshedAuthToken?> forceRefresh() {
    refreshCalls++;
    return pendingRefresh.future;
  }

  @override
  Future<void> signOut() async {
    onSignOut?.call();
    signOutCalls++;
    if (failSignOut) throw StateError('Firebase sign-out failed');
  }
}
